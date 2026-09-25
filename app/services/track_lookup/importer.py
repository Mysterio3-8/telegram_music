"""Добавление трека по свободному запросу пользователя.

Находим лучшее совпадение во всех источниках и загружаем из того, где нашли:
SoundCloud отдаёт чистое аудио как есть, YouTube — с приведением к mp3.
"""
import asyncio
import logging
from dataclasses import replace

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Track
from app.services.soundcloud import download_soundcloud_audio
from app.services.track_lookup.providers import (
    SOURCE_SOUNDCLOUD,
    search_soundcloud,
    search_youtube,
)
from app.services.track_lookup.metadata import candidate_metadata  # noqa: F401 — прежнее место
from app.services.track_lookup.ranking import Candidate
from app.services.youtube.downloader import DownloadedAudio, download_audio
from app.services.youtube.user_import import (
    UserImportRejected,
    extract_video_id,
    import_downloaded_audio,
)
from app.services.track_lookup import find_track, is_track_duration

logger = logging.getLogger(__name__)

NOT_FOUND_MESSAGE = (
    "Не нашли такой трек. Уточните исполнителя и название — например «Kizaru Фейк Айди»."
)


def download_candidate(candidate: Candidate) -> DownloadedAudio | None:
    """Загружает найденный трек из его источника — всегда в mp3 (приоритет владельца:
    пользователю уходит только mp3, с оригинальной обложкой источника)."""
    if candidate.source == SOURCE_SOUNDCLOUD and candidate.snippet:
        return None  # оба пути SoundCloud отдадут 30-секундное превью
    if candidate.source == SOURCE_SOUNDCLOUD:
        # Сперва прямой путь через API v2: 0,5 сек против 7,0 сек у yt-dlp
        # (замер прода 21.09). Не вышло — ниже прежний путь, он умеет HLS и DRM.
        from app.services.soundcloud_fast import fast_download

        fast = fast_download(candidate.url)
        if fast is not None:
            return fast
        result = download_soundcloud_audio(candidate.url, as_mp3=True)
        return result[0] if result else None
    video_id = extract_video_id(candidate.url)
    return download_audio(video_id, as_mp3=True) if video_id else None


MAX_DOWNLOAD_ATTEMPTS = 6
# Замена отличается по длительности больше чем на 12% — это уже другая запись:
# ускоренная версия короче на 20–25%, slowed длиннее, ремикс — как повезёт.
_DURATION_TOLERANCE = 0.12
# Ниже этого счёта «замена» — просто другой трек из выдачи того же артиста
_REPLACEMENT_MIN_SCORE = 0.45
# Второй, мягкий проход — когда строгих замен нет или ни одна не скачалась.
# Живой прогон 25.09: официальный «New Choppa» на SoundCloud длится 2:06, а все
# полные копии — 2:52; строгий порог отсёк их, и человек получил 30-секундное
# превью. Без пометок версий и с тем же названием разница в длине — это чаще
# другое издание (интро, радио-версия), чем подделка.
_RELAXED_DURATION_TOLERANCE = 0.4
_RELAXED_MIN_SCORE = 0.9


def is_same_recording(
    original: Candidate,
    query: str,
    alternative: Candidate,
    tolerance: float = _DURATION_TOLERANCE,
    min_score: float = _REPLACEMENT_MIN_SCORE,
) -> bool:
    """Годится ли соседний аплоад вместо недоступного оригинала.

    Прогон 25.09: альбом Pop Smoke (официальные треки под DRM) пришёл почти
    целиком подменённым — «Slowed + Reverb», «(Fast)», «Piano Cover», чужие
    ремиксы и «Type Beat». Перебор брал любого соседа из выдачи без проверки.
    Лучше честное «не удалось скачать», чем ускоренная копия под видом трека.
    """
    from app.services.track_lookup.ranking import match_score, version_penalty
    from app.services.title_quality import is_beat_or_instrumental

    wanted = original.full_title
    if version_penalty(wanted, alternative.full_title) < 1.0:
        return False
    if is_beat_or_instrumental(alternative.full_title) and not is_beat_or_instrumental(wanted):
        return False
    if original.duration and alternative.duration:
        if abs(alternative.duration - original.duration) > original.duration * tolerance:
            return False
    return match_score(query, alternative) >= min_score


def _replacement_order(original: Candidate, query: str, alternatives: list[Candidate]) -> list[Candidate]:
    """Сперва точные копии, за ними — то же название в другой длине (см. выше)."""
    strict, relaxed = [], []
    for alternative in alternatives:
        if alternative.snippet:
            continue  # та же беда, что у оригинала, — попытку не тратим
        if is_same_recording(original, query, alternative):
            strict.append(alternative)
        elif is_same_recording(
            original, query, alternative,
            tolerance=_RELAXED_DURATION_TOLERANCE, min_score=_RELAXED_MIN_SCORE,
        ):
            relaxed.append(alternative)
        else:
            logger.info("Замена отклонена, другая запись: «%s»", alternative.full_title)
    return strict + relaxed


def _interleave(*groups: list[Candidate]) -> list[Candidate]:
    """Перемешивает выдачу источников по очереди: первый из SC, первый из YT, второй
    из SC и так далее.

    Зачем: раньше замены брались срезом из склеенного списка, а склейка шла
    источник за источником — то есть все попытки съедал ОДИН источник, и до
    второго перебор не доходил. Для западного трека это было фатально: список
    начинался с YouTube, YouTube с серверного IP регулярно отвечает антиботом, и
    человек получал «трек под защитой», хотя на SoundCloud рядом лежала
    качающаяся копия, до которой мы просто не дошли.
    """
    result: list[Candidate] = []
    for row in range(max((len(group) for group in groups), default=0)):
        for group in groups:
            if row < len(group):
                result.append(group[row])
    return result


def download_with_fallback(candidate: Candidate) -> DownloadedAudio | None:
    """Скачивает выбранный трек, а если не вышло — соседние варианты того же трека.

    Часть треков на SoundCloud под DRM: yt-dlp отвечает «This video is DRM
    protected», и скачать их нельзя в принципе. По полям API они неотличимы от
    обычных — у DRM-«Blinding Lights» и у качающегося «ЗА ДЕНЬГИ ДА» одинаковые
    policy=MONETIZE, monetization=AD_SUPPORTED, streamable=True. Значит отфильтровать
    заранее нечем, зато почти всегда рядом в выдаче лежит тот же трек в чужом
    аплоаде — и он качается.

    Раньше мы в этом месте писали «попробуйте соседний вариант из списка», то есть
    просили человека сделать перебор руками. Теперь перебираем сами.
    """
    audio = download_candidate(candidate)
    if audio is not None:
        return audio

    artist, title = candidate_metadata(candidate)
    query = f"{artist} {title}".strip()
    logger.info("Не скачался «%s» — ищу замену по «%s»", candidate.title, query)

    # Под DRM лежат западные мейджоры, а их официальные загрузки есть на YouTube
    # («Исполнитель - Topic»). Поэтому замену ищем в ОБОИХ источниках и пробуем их
    # вперемежку: у каждого свой способ отказать (SoundCloud — DRM, YouTube —
    # антибот с серверного IP), и попытки не должен съедать один из них.
    from app.services.track_lookup import is_russian_repertoire

    sources = (
        (search_soundcloud, search_youtube)
        if is_russian_repertoire(query)
        else (search_youtube, search_soundcloud)
    )
    groups: list[list[Candidate]] = []
    for source in sources:
        try:
            groups.append(list(source(query, limit=MAX_DOWNLOAD_ATTEMPTS + 1)))
        except Exception:  # noqa: BLE001 — один источник отвалился, второй ещё есть
            logger.warning("Замена: источник %s не ответил", source.__name__, exc_info=True)
            groups.append([])

    seen = {candidate.url}
    unique: list[Candidate] = []
    for alternative in _interleave(*groups):
        if alternative.url not in seen:
            seen.add(alternative.url)
            unique.append(alternative)
    attempts = 0
    for alternative in _replacement_order(candidate, query, unique):
        attempts += 1
        if attempts > MAX_DOWNLOAD_ATTEMPTS:
            break
        audio = download_candidate(alternative)
        if audio is not None:
            logger.info(
                "Замена нашлась с %s попытки: «%s» (%s)",
                attempts, alternative.title, alternative.source,
            )
            return audio

    logger.warning(
        "«%s»: не скачался ни оригинал, ни %s замен из %s источников",
        query, attempts, len([group for group in groups if group]),
    )
    return None


async def _user_by_telegram_id(session: AsyncSession, telegram_id: int):
    from app.services.users import get_user_by_telegram_id

    return await get_user_by_telegram_id(session, telegram_id)


async def import_candidate(
    session: AsyncSession,
    bot: Bot,
    candidate: Candidate,
    telegram_id: int,
    save_to_library: bool = True,
) -> tuple[Track, bool]:
    """Загружает выбранного пользователем кандидата.

    Отличие от import_by_query: кандидат уже выбран человеком, поиск не повторяем
    и по длительности не придираемся — раз выбрал, значит именно это и хотел.

    save_to_library=False — «просто пришли послушать»: трек уходит в общий
    каталог, но не в личную библиотеку."""
    from app.services.library import add_to_library
    from app.services.search import find_track_by_source_url

    # Этот же кандидат уже приезжал — отдаём готовое, скачивать нечего. Проверка
    # по ссылке, а не по «исполнитель — название»: заголовок в выдаче и в
    # скачанном файле расходятся, и сверка по нему промахивалась.
    existing = await find_track_by_source_url(session, candidate.url)
    if existing is None:
        existing = await _wait_foreign_import(session, candidate.url)
    if existing is not None:
        if save_to_library:
            user = await _user_by_telegram_id(session, telegram_id)
            if user is not None:
                await add_to_library(session, user.id, existing.id)
        logger.info("Кандидат уже в базе: %s → track=%s", candidate.url, existing.id)
        return existing, False

    from app.services import import_lock

    # Замок ставим сами только сейчас: его держатель уже проверил базу и никого
    # не ждёт. Второй пришедший увидит замок в _wait_foreign_import выше.
    locked = import_lock.acquire(candidate.url)
    try:
        return await _download_and_import(session, bot, candidate, telegram_id, save_to_library)
    finally:
        if locked:
            import_lock.release(candidate.url)


# Сколько ждём чужой импорт той же ссылки, прежде чем качать самим. Дольше
# самого медленного пути (yt-dlp + ffmpeg + минт) смысла нет: значит, тот
# импорт упал, и замок висит до истечения.
_FOREIGN_WAIT_SECONDS = 90.0
_FOREIGN_POLL_SECONDS = 1.0


async def _wait_foreign_import(session: AsyncSession, url: str) -> Track | None:
    """Ссылку уже качает другой поток или процесс — дожидаемся его трека.

    🔴 Без этого 23.09 появилась пара 33007/33008 «BONES — Dashboard»: две
    записи одной ссылки с разницей в секунду.
    """
    from app.services import import_lock
    from app.services.search import find_track_by_source_url

    if not import_lock.is_locked(url):
        return None
    loop = asyncio.get_running_loop()
    deadline = loop.time() + _FOREIGN_WAIT_SECONDS
    while loop.time() < deadline:
        await asyncio.sleep(_FOREIGN_POLL_SECONDS)
        # ⚠️ Новая транзакция на каждой проверке: в WAL сессия видит снимок,
        # сделанный на первом чтении, и чужую вставку не заметила бы никогда.
        await session.rollback()
        track = await find_track_by_source_url(session, url)
        if track is not None:
            return track
        if not import_lock.is_locked(url):
            break  # чужой импорт закончился неудачей — пробуем сами
    return await find_track_by_source_url(session, url)


async def _download_and_import(
    session: AsyncSession, bot: Bot, candidate: Candidate, telegram_id: int, save_to_library: bool
) -> tuple[Track, bool]:
    audio = await asyncio.to_thread(download_with_fallback, candidate)
    if audio is None:
        raise UserImportRejected(
            "Этот трек скачать не вышло — у источника он под защитой. "
            "Попробуйте другое название или соседний вариант."
        )
    # Выдача поиска знает автора и обложку; при скачивании источник их иногда не
    # отдаёт. Подставляем известное, иначе трек уходит человеку без обложки и
    # подписанный «Исполнитель».
    audio = replace(
        audio,
        uploader=audio.uploader or (candidate.artist or ""),
        thumbnail_url=audio.thumbnail_url or (candidate.cover_url or ""),
    )
    track, created = await import_downloaded_audio(
        session, bot, audio, telegram_id,
        save_to_library=save_to_library,
        source_url=candidate.url,
        # Отпечаток тут не считаем: fpcalc декодирует трек целиком, а на боксе с
        # одним ядром это секунды ожидания живого человека. Дубликат мы и так
        # ловим раньше — по ссылке источника и по «исполнитель — название».
        # Отпечаток нужен там, где файл приносит пользователь и ссылки нет.
        with_fingerprint=False,
    )
    logger.info(
        "Импорт кандидата источник=%s user=%s → track=%s (created=%s)",
        candidate.source, telegram_id, track.id, created,
    )
    return track, created


async def import_by_query(
    session: AsyncSession, bot: Bot, query: str, telegram_id: int
) -> tuple[Track, bool]:
    """Находит трек по запросу и добавляет пользователю. Возвращает (трек, создан_ли)."""
    candidate = await asyncio.to_thread(find_track, query)
    if candidate is None:
        raise UserImportRejected(NOT_FOUND_MESSAGE)

    audio = await asyncio.to_thread(download_with_fallback, candidate)
    if audio is None:
        raise UserImportRejected(NOT_FOUND_MESSAGE)

    # Длительность по факту: в выдаче её могло не быть (duration=0) или она врала.
    # Здесь отсекаем 10-секундные обрезки и часовые миксы окончательно.
    if not is_track_duration(audio.duration):
        logger.info(
            "Поиск «%s»: отклонён по длительности %s сек (%s)",
            query, audio.duration, candidate.url,
        )
        raise UserImportRejected(NOT_FOUND_MESSAGE)

    track, created = await import_downloaded_audio(session, bot, audio, telegram_id)
    logger.info(
        "Импорт по запросу «%s» источник=%s user=%s → track=%s (created=%s)",
        query, candidate.source, telegram_id, track.id, created,
    )
    return track, created

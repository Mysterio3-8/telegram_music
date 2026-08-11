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
    if candidate.source == SOURCE_SOUNDCLOUD:
        result = download_soundcloud_audio(candidate.url, as_mp3=True)
        return result[0] if result else None
    video_id = extract_video_id(candidate.url)
    return download_audio(video_id, as_mp3=True) if video_id else None


MAX_DOWNLOAD_ATTEMPTS = 6


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

    tried = {candidate.url}
    attempts = 0
    for alternative in _interleave(*groups):
        if alternative.url in tried:
            continue
        tried.add(alternative.url)
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


def candidate_metadata(candidate: Candidate) -> tuple[str, str]:
    """(исполнитель, название) кандидата — теми же правилами, что и при импорте.

    Нужна ДО скачивания: по этой паре смотрим, не залит ли трек уже, и экономим
    целую загрузку. После скачивания метаданные пересчитываются по факту файла.
    """
    from app.services.title_parser import parse_title

    fallback = (candidate.artist or "").removesuffix(" - Topic").strip() or "Исполнитель"
    return parse_title(candidate.title, fallback)


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
    if existing is not None:
        if save_to_library:
            user = await _user_by_telegram_id(session, telegram_id)
            if user is not None:
                await add_to_library(session, user.id, existing.id)
        logger.info("Кандидат уже в базе: %s → track=%s", candidate.url, existing.id)
        return existing, False

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

"""Источники поиска трека. Вся сеть — здесь; ранжирование в ranking.py.

Поисковый запрос идёт сразу во все источники: отказ одного (бан, сеть, пустая
выдача) не должен ронять поиск целиком — берём то, что ответило.
"""
import logging
import re

from app.services.soundcloud import list_soundcloud_entries
from app.services.track_lookup.ranking import Candidate
from app.services.youtube.downloader import search_videos

logger = logging.getLogger(__name__)

SOURCE_SOUNDCLOUD = "soundcloud"
SOURCE_YOUTUBE = "youtube"

_WATCH_URL = "https://www.youtube.com/watch?v={video_id}"


def search_soundcloud(query: str, limit: int = 5) -> list[Candidate]:
    """Кандидаты SoundCloud.

    Сперва прямой API поверх постоянного соединения: yt-dlp поднимает новое
    TLS-соединение на каждый вызов, а это 8.5 сек против 0.7 сек по живому
    (замер). yt-dlp остаётся запасным путём — если API забанят или он сменит
    формат, поиск продолжит работать, просто медленнее.
    """
    from app.services.soundcloud_api import search_tracks

    direct = search_tracks(query, limit)
    if direct:
        return direct
    logger.info("SoundCloud API пуст — иду через yt-dlp «%s»", query)
    # sleep_requests=0: ответа ждёт живой человек, а обходим одну поисковую выдачу,
    # а не весь профиль артиста — пауза между запросами здесь только тормозит
    entries = list_soundcloud_entries(f"scsearch{max(1, limit)}:{query}", sleep_requests=0)
    return [_soundcloud_candidate(entry.url, entry.title, entry.duration, entry.uploader, entry.cover_url) for entry in entries]


def soundcloud_candidate_fields(title: str, uploader: str | None) -> tuple[str, str]:
    """(исполнитель, название) для трека SoundCloud.

    Заливать чужую музыку там может кто угодно, поэтому имя аккаунта — это НЕ
    исполнитель: в выдаче по «Кизару» стояли «yarik», «Kogo», «original pidors».
    Настоящий артист почти всегда в самом заголовке («Кизару - Зеркало»), и
    разбираем мы его тем же parse_title, каким подписывается трек при импорте —
    иначе кнопка в боте и подпись пришедшего файла говорили бы разное.

    Автора аккаунта оставляем запасным вариантом: у части треков заголовок это
    одно слово («Секс»), и тогда без него исполнителя взять неоткуда.
    """
    from app.services.title_parser import parse_title

    return parse_title(title, (uploader or "").strip())


def _soundcloud_candidate(url: str, title: str, duration, uploader, cover_url) -> Candidate:
    artist, clean_title = soundcloud_candidate_fields(title, uploader)
    return Candidate(
        source=SOURCE_SOUNDCLOUD,
        url=url,
        title=clean_title or title,
        duration=_to_seconds(duration),
        # В сопоставление (full_title) идёт разобранный артист, а не владелец
        # аккаунта: иначе «Кизару — Зеркало» от четырёх разных заливщиков
        # выглядели как четыре разных трека и занимали пол-страницы выдачи.
        artist=artist or None,
        uploader=(uploader or "").strip() or None,
        cover_url=cover_url or None,
    )


def _to_seconds(value) -> int:
    """SoundCloud отдаёт длительность в миллисекундах, yt-dlp местами — в секундах.
    Разводим по величине: 20 000 «секунд» — это 5,5 часов, такого трека не бывает."""
    number = int(value or 0)
    return number // 1000 if number > 20_000 else number


_TOPIC_CHANNEL_SUFFIX = "- Topic"
# Тире у людей какое угодно: минус, длинное, короткое, неразрывное. Приводим всё
# к обычному дефису, иначе «Fake ID – kizaru» не опознаётся как трек.
_DASHES = "‐‑‒–—―−─-"
_DASH_RE = re.compile(f"[{_DASHES}]")


def looks_like_music(candidate: Candidate) -> bool:
    """Похож ли ролик YouTube на трек, а не на видео о чём-нибудь.

    Нужно потому, что YouTube — это видеохостинг, а не музыкальный каталог: запрос
    «секс» приносил ролики про игрушки и про биологию. Тему фильтровать нельзя (в
    песнях бывает что угодно), поэтому смотрим на форму:

    — канал «Исполнитель - Topic» это автоматический музыкальный канал YouTube;
    — «Исполнитель - Название» — обычная подпись трека, у роликов её почти не бывает.

    Всё остальное с YouTube не берём. Он у нас фолбэк, а не источник каталога:
    лучше не показать сомнительное, чем показать не-музыку.
    """
    if (candidate.uploader or "").strip().endswith(_TOPIC_CHANNEL_SUFFIX):
        return True
    # ⚠️ Разобранный исполнитель — это и есть признак «заголовок был подписан
    # „Артист - Название“». Проверять тире в самом названии больше нельзя: с
    # 14.08 мы это тире срезаем при разборе, и условие по title стало бы всегда
    # ложным — YouTube выпал бы из выдачи целиком.
    if candidate.artist:
        return True
    return " - " in _DASH_RE.sub("-", candidate.title)


def youtube_candidate_fields(title: str) -> tuple[str | None, str]:
    """(исполнитель, название) для ролика YouTube — разбором ЗАГОЛОВКА.

    Имя канала сюда не пускаем принципиально: у YouTube это «GOLDEN SOUND» или
    «Sueta music», то есть заливщик, а не артист. Пусти мы его в `artist`,
    сломался бы дедуп с SoundCloud — один трек считался бы двумя.

    Зато сам заголовок почти всегда подписан «Kizaru - FAKE ID», и это
    настоящий исполнитель. Без разбора он оставался пустым, и человек видел в
    списке «Исполнитель — Kizaru - FAKE ID ❤️» вместо «Kizaru — FAKE ID».
    """
    from app.services.title_parser import parse_title

    artist, clean = parse_title(title, "")
    # ⚠️ parse_title без разделителя отдаёт не пустую строку, а «Unknown» — так
    # он устроен для импорта, где исполнитель обязан быть чем-то заполнен. Нам
    # нужно обратное: нет разделителя, значит исполнителя в заголовке не было, и
    # выдумывать его не из чего. Пусто честнее, чем «Unknown» в кнопке.
    if artist == "Unknown":
        artist = ""
    return (artist or None), (clean or title)


def _youtube_candidate(entry) -> Candidate:
    artist, title = youtube_candidate_fields(entry.title)
    return Candidate(
        source=SOURCE_YOUTUBE,
        url=_WATCH_URL.format(video_id=entry.video_id),
        title=title,
        artist=artist,
        duration=entry.duration,
        # Канал — только в uploader: в artist его пускать нельзя, иначе имя
        # канала попадёт в сопоставление и сломает дедуп с SoundCloud
        uploader=entry.uploader or None,
        cover_url=entry.cover_url or None,
        # «Исполнитель - Topic» — автоматический канал, который YouTube
        # заводит по поставке от дистрибьютора. Это официальный релиз по
        # определению, в отличие от перезалива на обычном канале.
        official=(entry.uploader or "").strip().endswith(_TOPIC_CHANNEL_SUFFIX),
    )


def search_youtube(query: str, limit: int = 5) -> list[Candidate]:
    """Кандидаты YouTube и YouTube Music (общая поисковая выдача yt-dlp)."""
    return [
        _youtube_candidate(entry)
        for entry in search_videos(query, limit=limit, sleep_requests=0)
    ]


# Порядок важен только при равном совпадении: SoundCloud даёт чистое аудио без клипов
PROVIDERS = (search_soundcloud, search_youtube)


def collect_candidates(query: str, limit: int = 5) -> list[Candidate]:
    """Опрашивает все источники. Упавший источник логируется и пропускается."""
    found: list[Candidate] = []
    for provider in PROVIDERS:
        try:
            found.extend(provider(query, limit))
        except Exception:  # noqa: BLE001 — источник мог забанить/отвалиться, идём к следующему
            logger.warning("Поиск трека: источник %s не ответил", provider.__name__, exc_info=True)
    return found

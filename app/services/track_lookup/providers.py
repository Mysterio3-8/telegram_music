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
    return [
        Candidate(
            source=SOURCE_SOUNDCLOUD,
            url=entry.url,
            title=entry.title,
            duration=_to_seconds(entry.duration),
            # Автор идёт в сопоставление (full_title): официальный аплоад артиста
            # обгоняет чужой реаплоад с похожим названием
            artist=entry.uploader or None,
            uploader=entry.uploader or None,
            cover_url=entry.cover_url or None,
        )
        for entry in entries
    ]


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
    return " - " in _DASH_RE.sub("-", candidate.title)


def search_youtube(query: str, limit: int = 5) -> list[Candidate]:
    """Кандидаты YouTube и YouTube Music (общая поисковая выдача yt-dlp)."""
    return [
        Candidate(
            source=SOURCE_YOUTUBE,
            url=_WATCH_URL.format(video_id=entry.video_id),
            title=entry.title,
            duration=entry.duration,
            # Канал — только в uploader: в artist его пускать нельзя, иначе имя
            # канала попадёт в сопоставление и сломает дедуп с SoundCloud
            uploader=entry.uploader or None,
            cover_url=entry.cover_url or None,
        )
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

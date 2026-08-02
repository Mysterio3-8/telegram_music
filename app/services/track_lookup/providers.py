"""Источники поиска трека. Вся сеть — здесь; ранжирование в ranking.py.

Поисковый запрос идёт сразу во все источники: отказ одного (бан, сеть, пустая
выдача) не должен ронять поиск целиком — берём то, что ответило.
"""
import logging

from app.services.soundcloud import list_soundcloud_entries
from app.services.track_lookup.ranking import Candidate
from app.services.youtube.downloader import search_videos

logger = logging.getLogger(__name__)

SOURCE_SOUNDCLOUD = "soundcloud"
SOURCE_YOUTUBE = "youtube"

_WATCH_URL = "https://www.youtube.com/watch?v={video_id}"


def search_soundcloud(query: str, limit: int = 5) -> list[Candidate]:
    """Кандидаты SoundCloud. Длительность приходит прямо из выдачи (extract_flat) —
    мусор по времени отсеивается ДО скачивания, поэтому поиск укладывается в секунды."""
    entries = list_soundcloud_entries(f"scsearch{max(1, limit)}:{query}")
    return [
        Candidate(
            source=SOURCE_SOUNDCLOUD,
            url=entry.url,
            title=entry.title,
            duration=_to_seconds(entry.duration),
            # Автор идёт в сопоставление (full_title): официальный аплоад артиста
            # обгоняет чужой реаплоад с похожим названием
            artist=entry.uploader or None,
            cover_url=entry.cover_url or None,
        )
        for entry in entries
    ]


def _to_seconds(value) -> int:
    """SoundCloud отдаёт длительность в миллисекундах, yt-dlp местами — в секундах.
    Разводим по величине: 20 000 «секунд» — это 5,5 часов, такого трека не бывает."""
    number = int(value or 0)
    return number // 1000 if number > 20_000 else number


def search_youtube(query: str, limit: int = 5) -> list[Candidate]:
    """Кандидаты YouTube и YouTube Music (общая поисковая выдача yt-dlp)."""
    return [
        Candidate(
            source=SOURCE_YOUTUBE,
            url=_WATCH_URL.format(video_id=entry.video_id),
            title=entry.title,
            duration=entry.duration,
            cover_url=entry.cover_url or None,
        )
        for entry in search_videos(query, limit=limit)
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

"""Прямая ссылка на аудиопоток кандидата — чтобы Mini App начинал играть сразу,
не дожидаясь скачивания и заливки в Telegram.

yt-dlp умеет отдать URL формата без загрузки файла. Ссылка живёт недолго и
привязана к сессии, поэтому кэшируем её отдельно от поисковой выдачи и коротко:
устаревшая выдача — мелочь, устаревшая ссылка обрывает воспроизведение.

Прогрессивный поток (обычный http-файл) предпочтительнее HLS: <audio> в Safari
играет и то и другое, но по прогрессивному работает перемотка через Range.
"""
import logging

import yt_dlp

from app.services.track_lookup.providers import SOURCE_SOUNDCLOUD
from app.services.track_lookup.ranking import Candidate
from app.services.youtube.downloader import _base_opts

logger = logging.getLogger(__name__)

_HLS_PROTOCOLS = ("m3u8", "m3u8_native")


def pick_stream_url(info: dict) -> str | None:
    """Лучший аудиоформат из ответа yt-dlp: прогрессивный впереди HLS."""
    formats = [f for f in (info.get("formats") or []) if f.get("url")]
    audio_only = [f for f in formats if f.get("vcodec") in (None, "none")]
    pool = audio_only or formats
    progressive = [f for f in pool if f.get("protocol") not in _HLS_PROTOCOLS]
    best = (progressive or pool or [None])[-1]
    if best:
        return best["url"]
    return info.get("url")


def resolve_stream_url(candidate: Candidate) -> str | None:
    """Прямая ссылка на аудио кандидата. None — источник не отдал поток."""
    is_soundcloud = candidate.source == SOURCE_SOUNDCLOUD
    opts = {
        **_base_opts(impersonate=is_soundcloud, use_proxy=is_soundcloud),
        "skip_download": True,
        "noplaylist": True,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(candidate.url, download=False)
    except Exception:  # noqa: BLE001 — источник отвалился/удалил трек
        logger.warning("Поток не резолвится: %s", candidate.url, exc_info=True)
        return None
    return pick_stream_url(info or {})

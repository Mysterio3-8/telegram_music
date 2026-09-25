"""Быстрое скачивание трека с SoundCloud напрямую через API v2 (21.09).

🔴 Замер прода 21.09 (жалоба владельца «треки очень долго присылаются»):
скачивание одного трека через yt-dlp — **7,0 сек**, хотя сам файл 3,4 МБ едет за
0,15 сек. Остальное — разбор страницы и запуск постобработки. Тот же трек через
API v2: resolve 0,20 + карточка трека 0,06 + ссылка на поток 0,07 + скачивание
0,15 = **0,5 сек**. То есть 6,5 секунды из ожидания человека уходили ни на что.

Берём только `progressive` + `audio/mpeg`: это готовый mp3, его не надо ни
склеивать из кусков, ни перекодировать (ffmpeg на одном ядре — ещё секунды).
Нет такого варианта (часть треков отдаётся только по HLS) — возвращаем None, и
вызывающий идёт прежним путём через yt-dlp. То же при любой ошибке: быстрый путь
не имеет права отнимать у человека трек, он может только ускорить выдачу.
"""
from __future__ import annotations

import logging
import urllib.request

from app.services.youtube.downloader import DownloadedAudio

logger = logging.getLogger(__name__)

# Кусок больше этого — не музыка, а чья-то ошибка: не тянем в память 961-МБ бокса
MAX_BYTES = 60 * 1024 * 1024
DOWNLOAD_TIMEOUT = 45


def _progressive_mp3(track: dict) -> str | None:
    for item in ((track.get("media") or {}).get("transcodings") or []):
        fmt = item.get("format") or {}
        if fmt.get("protocol") == "progressive" and "mpeg" in (fmt.get("mime_type") or ""):
            return item.get("url")
    return None


def _fetch_bytes(url: str) -> bytes | None:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT) as response:
        data = response.read(MAX_BYTES + 1)
    if not data or len(data) > MAX_BYTES:
        return None
    return data


def fast_download(url: str) -> DownloadedAudio | None:
    """Трек по ссылке SoundCloud. None — быстрый путь не вышел, зовите yt-dlp."""
    from app.services.mojibake import repair
    from app.services.soundcloud_api import api_get, is_snippet

    try:
        track = api_get("/resolve", {"url": url})
        if not isinstance(track, dict):
            return None
        if track.get("kind") != "track":
            return None  # ссылка на сет или профиль — это не наш путь
        if is_snippet(track):
            # Превью Go+ на 30 сек под видом трека хуже, чем отказ: отказ
            # запускает поиск полной копии (download_with_fallback)
            logger.info("Быстрое скачивание: %s — только превью Go+, пропускаю", url)
            return None
        stream = _progressive_mp3(track)
        if not stream and track.get("id"):
            # У карточки из поиска список вариантов бывает урезан — берём полную
            full = api_get(f"/tracks/{track['id']}")
            if isinstance(full, dict):
                track = full
                stream = _progressive_mp3(track)
        if not stream:
            return None  # только HLS — пусть собирает yt-dlp

        link = api_get(stream.replace("https://api-v2.soundcloud.com", ""))
        if not isinstance(link, dict) or not link.get("url"):
            return None
        data = _fetch_bytes(link["url"])
        if not data:
            return None
    except Exception:  # noqa: BLE001 — любой сбой = прежний путь, человек без трека не остаётся
        logger.info("Быстрое скачивание не вышло для %s, иду через yt-dlp", url, exc_info=True)
        return None

    from app.services.soundcloud import upscale_soundcloud_artwork

    duration = int((track.get("full_duration") or track.get("duration") or 0) / 1000)
    publisher = track.get("publisher_metadata") or {}
    return DownloadedAudio(
        data=data,
        file_format="mp3",
        duration=duration,
        video_title=repair((track.get("title") or "").strip()),
        uploader=repair(
            (publisher.get("artist") or (track.get("user") or {}).get("username") or "").strip()
        ),
        # 🔴 artwork_url у SoundCloud приходит суффиксом «-large» — это 100×100 и
        # 4 КБ. Именно он вшивался в файл и уходил в Mini App с 21.09, когда
        # быстрый путь заменил yt-dlp: «картинки он в ужасном качестве присылает»
        # (владелец 21.09). Апскейлим к t500x500 — тот же CDN, другой суффикс.
        thumbnail_url=upscale_soundcloud_artwork(track.get("artwork_url") or ""),
        album=repair((publisher.get("album_title") or "").strip()),
    )

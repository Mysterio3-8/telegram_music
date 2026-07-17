"""SoundCloud как источник минусов (запрос владельца): скачивание через yt-dlp.

Принимает ссылку на трек, профиль или сет — профиль/сет разворачивается в список
треков (extract_flat), каждый скачивается отдельно. Артист берётся из uploader,
название — из title. Байты живут только в памяти до минта через бота.
"""
import logging
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

import yt_dlp

from app.config import settings
from app.services.youtube.downloader import DownloadedAudio, _base_opts, _read_supported

logger = logging.getLogger(__name__)

_SOUNDCLOUD_RE = re.compile(r"(?:https?://)?(?:www\.|m\.|on\.)?soundcloud\.com/\S+")


@dataclass(frozen=True)
class SoundcloudEntry:
    url: str
    title: str


def is_soundcloud_link(text: str) -> bool:
    return bool(_SOUNDCLOUD_RE.search(text or ""))


def extract_soundcloud_url(text: str) -> str | None:
    match = _SOUNDCLOUD_RE.search(text or "")
    if not match:
        return None
    url = match.group(0)
    return url if url.startswith("http") else f"https://{url}"


def list_soundcloud_entries(url: str) -> list[SoundcloudEntry]:
    """Трек → один элемент; профиль/сет → список треков (без скачивания)."""
    opts = {**_base_opts(), "extract_flat": "in_playlist", "skip_download": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    if info is None:
        return []
    return collect_soundcloud_entries(info)


def collect_soundcloud_entries(info: dict) -> list[SoundcloudEntry]:
    """Чистый разбор ответа yt-dlp (отделён от сети для тестов)."""
    entries: list[SoundcloudEntry] = []
    seen: set[str] = set()

    def walk(node: dict | None) -> None:
        if node is None:
            return
        if node.get("entries") is not None:
            for child in node["entries"]:
                walk(child)
            return
        entry_url = node.get("url") or node.get("webpage_url")
        if entry_url and "soundcloud.com" in entry_url and entry_url not in seen:
            seen.add(entry_url)
            entries.append(SoundcloudEntry(entry_url, node.get("title") or entry_url))

    walk(info)
    return entries


def download_soundcloud_audio(url: str) -> tuple[DownloadedAudio, str] | None:
    """Скачивает один трек. Возвращает (аудио, uploader) или None."""
    with tempfile.TemporaryDirectory() as tmp:
        opts = {
            **_base_opts(),
            "format": "bestaudio/best",
            "outtmpl": str(Path(tmp) / "sc.%(ext)s"),
            "noplaylist": True,
            "retries": settings.youtube_max_retries,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
        if info is None:
            return None
        files = [p for p in Path(tmp).glob("sc.*") if not p.name.endswith(".conv.m4a")]
        if not files:
            return None
        data, file_format = _read_supported(files[0])
        audio = DownloadedAudio(
            data=data,
            file_format=file_format,
            duration=int(info.get("duration") or 0),
            video_title=info.get("title") or url,
        )
        return audio, (info.get("uploader") or "").strip()

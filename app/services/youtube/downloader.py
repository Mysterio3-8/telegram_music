"""Обёртка над yt-dlp: список видео канала/плейлиста и скачивание аудиодорожки.

Только аудио, без видео и обложек (доп. ТЗ, §5, §6). Предпочтение — m4a bestaudio
без лишнего перекодирования; редкий неподдерживаемый контейнер ремуксится в m4a.
"""
import logging
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import yt_dlp

from app.config import settings
from app.services.uploads import SUPPORTED_FORMATS

logger = logging.getLogger(__name__)

_VIDEO_ID_LENGTH = 11


@dataclass(frozen=True)
class VideoEntry:
    video_id: str
    title: str


@dataclass(frozen=True)
class DownloadedAudio:
    data: bytes
    file_format: str
    duration: int
    video_title: str
    uploader: str = ""  # канал/автор — fallback для исполнителя, чтобы не было «Unknown»
    thumbnail_url: str = ""  # обложка источника — вшивается в файл и показывается в Mini App
    album: str = ""  # альбом из метаданных источника (SoundCloud отдаёт для сетов)


def fetch_thumbnail(url: str) -> bytes:
    """Скачивает картинку обложки. Пустые байты — не критично, трек живёт без неё."""
    if not url:
        return b""
    import urllib.request

    try:
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=15) as response:
            data = response.read(5 * 1024 * 1024)  # обложки больше 5 МБ не бывают
        return data
    except Exception:  # noqa: BLE001 — сеть/404: обложка опциональна
        logger.warning("Не удалось скачать обложку %s", url)
        return b""


@dataclass(frozen=True)
class VideoInfo:
    video_id: str
    title: str
    duration: int
    is_live: bool


def _impersonate_target():
    """Chrome-impersonation (curl_cffi) — без него SoundCloud отдаёт 404 на частых/
    параллельных запросах. Если curl_cffi не установлен, тихо работаем без него."""
    try:
        from yt_dlp.networking.impersonate import ImpersonateTarget

        return ImpersonateTarget("chrome")
    except Exception:  # noqa: BLE001 — старый yt-dlp / нет curl_cffi
        return None


def _base_opts(impersonate: bool = False, use_proxy: bool = False) -> dict:
    """impersonate=True — Chrome-маскировка (curl_cffi), нужна SoundCloud (иначе 404
    на частых запросах). YouTube её не просит и на импersonation иногда отвечает
    403 (собственная система защиты реагирует на чужой TLS-отпечаток) — там она
    по умолчанию выключена.

    use_proxy=True — запрос уходит через следующий прокси из PROXY_LIST (ротация
    по кругу, services/proxies). Включаем только для SoundCloud-путей: массовая
    закачка 24/7 не должна светить IP сервера."""
    opts: dict = {
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
        # Анти-бан: пауза между HTTP-запросами при обходе профиля/плейлиста
        "sleep_interval_requests": 1,
    }
    if impersonate:
        target = _impersonate_target()
        if target is not None:
            opts["impersonate"] = target
    if use_proxy:
        from app.services.proxies import next_proxy

        proxy = next_proxy()
        if proxy:
            opts["proxy"] = proxy
    if settings.youtube_cookies_path and Path(settings.youtube_cookies_path).exists():
        opts["cookiefile"] = settings.youtube_cookies_path
    return opts


def normalize_source_url(url: str) -> str:
    """Плейлист — как есть; канал/handle — вкладка /videos для полного списка загрузок.
    YouTube Music — тот же контент под другим доменом: приводим к www.youtube.com,
    yt-dlp там надёжнее разворачивает каналы и плейлисты."""
    url = url.replace("music.youtube.com", "www.youtube.com")
    if "list=" in url or "/playlist" in url:
        return url
    if any(tab in url for tab in ("/videos", "/streams", "/shorts", "/featured")):
        return url
    return url.rstrip("/") + "/videos"


def _collect_entries(info: dict | None) -> list[VideoEntry]:
    entries: list[VideoEntry] = []
    seen: set[str] = set()

    def walk(node: dict | None) -> None:
        if node is None:
            return
        if node.get("entries") is not None:
            for child in node["entries"]:
                walk(child)
            return
        video_id = node.get("id")
        if video_id and len(video_id) == _VIDEO_ID_LENGTH and video_id not in seen:
            seen.add(video_id)
            entries.append(VideoEntry(video_id, node.get("title") or video_id))

    walk(info)
    return entries


def fetch_video_info(video_id: str) -> VideoInfo | None:
    """Метаданные одного видео без скачивания — для проверки лимитов ДО загрузки."""
    opts = {**_base_opts(), "skip_download": True, "noplaylist": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
    if info is None:
        return None
    return VideoInfo(
        video_id=video_id,
        title=info.get("title") or video_id,
        duration=int(info.get("duration") or 0),
        is_live=bool(info.get("is_live")),
    )


def list_videos(source_url: str) -> list[VideoEntry]:
    opts = {**_base_opts(), "extract_flat": "in_playlist", "skip_download": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(normalize_source_url(source_url), download=False)
    return _collect_entries(info)


def _read_supported(path: Path) -> tuple[bytes, str]:
    ext = path.suffix.lstrip(".").lower()
    if ext == "mp4":
        ext = "m4a"
    if ext in SUPPORTED_FORMATS:
        return path.read_bytes(), ext
    # Редкий фолбэк (webm/opus): ремукс в m4a
    converted = path.with_suffix(".conv.m4a")
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(path), "-vn", "-c:a", "aac", "-b:a", "192k", str(converted)],
        check=True,
        capture_output=True,
    )
    return converted.read_bytes(), "m4a"


def search_first_video(query: str) -> VideoEntry | None:
    """Первый результат поиска YouTube по запросу «исполнитель название».
    Нужен переносу плейлистов: чужие сервисы отдают только метаданные."""
    opts = {**_base_opts(), "extract_flat": "in_playlist", "skip_download": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"ytsearch1:{query}", download=False)
    entries = _collect_entries(info)
    return entries[0] if entries else None


def download_audio(video_id: str) -> DownloadedAudio | None:
    with tempfile.TemporaryDirectory() as tmp:
        opts = {
            **_base_opts(),
            "format": settings.youtube_audio_format,
            "outtmpl": str(Path(tmp) / "%(id)s.%(ext)s"),
            "noplaylist": True,
            "retries": settings.youtube_max_retries,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(
                f"https://www.youtube.com/watch?v={video_id}", download=True
            )
        if info is None:
            return None
        files = [p for p in Path(tmp).glob(f"{video_id}.*") if not p.name.endswith(".conv.m4a")]
        if not files:
            return None
        data, file_format = _read_supported(files[0])
        # yt-dlp у музыкальных загрузок кладёт исполнителя в artist/creator,
        # иначе берём имя канала — всё лучше, чем «Unknown»
        uploader = (
            info.get("artist")
            or info.get("creator")
            or info.get("uploader")
            or info.get("channel")
            or ""
        )
        return DownloadedAudio(
            data=data,
            file_format=file_format,
            duration=int(info.get("duration") or 0),
            video_title=info.get("title") or video_id,
            uploader=str(uploader).strip(),
            thumbnail_url=str(info.get("thumbnail") or ""),
            album=str(info.get("album") or "").strip(),
        )

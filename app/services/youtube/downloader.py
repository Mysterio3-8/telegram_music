"""Обёртка над yt-dlp: список видео канала/плейлиста и скачивание аудиодорожки.

Только аудио, без видео и обложек (доп. ТЗ, §5, §6). Предпочтение — m4a bestaudio
без лишнего перекодирования; редкий неподдерживаемый контейнер ремуксится в m4a.
"""
import logging
import subprocess
import tempfile
from urllib.parse import quote
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
    # Длительность и обложка из выдачи поиска (extract_flat отдаёт их для YouTube).
    # Живой поиск рисует карточки до скачивания и отсекает часовые миксы сразу.
    duration: int = 0
    cover_url: str = ""
    # Канал: «Исполнитель - Topic» — автоматический музыкальный канал YouTube,
    # по нему живой поиск отличает трек от ролика про что-нибудь
    uploader: str = ""


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


# Bot API: миниатюра — JPEG до 200 КБ, стороны до 320 px. Крупнее Telegram молча
# игнорирует, и трек показывается без обложки, хотя внутри файла она вшита.
TELEGRAM_THUMB_MAX_BYTES = 200 * 1024


def fetch_telegram_thumbnail(cover_url: str) -> bytes:
    """Маленькая копия обложки под миниатюру Telegram. Пусто — не нашли подходящей,
    трек уйдёт со вшитой обложкой и без превью в плеере (не критично)."""
    from app.services.soundcloud import thumbnail_soundcloud_artwork

    small_url = thumbnail_soundcloud_artwork(cover_url)
    if not small_url:
        return b""
    data = fetch_thumbnail(small_url)
    return data if 0 < len(data) <= TELEGRAM_THUMB_MAX_BYTES else b""


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


def _base_opts(
    impersonate: bool = False, use_proxy: bool = False, sleep_requests: int = 1
) -> dict:
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
        # Анти-бан: пауза между HTTP-запросами при обходе профиля/плейлиста.
        # sleep_requests=0 — для живого поиска: там ответа ждёт человек, а обход
        # идёт по одной поисковой выдаче, а не по всему профилю артиста.
        "sleep_interval_requests": sleep_requests,
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
            entries.append(
                VideoEntry(
                    video_id,
                    node.get("title") or video_id,
                    duration=int(node.get("duration") or 0),
                    cover_url=_entry_thumbnail(node),
                    uploader=str(node.get("uploader") or node.get("channel") or "").strip(),
                )
            )

    walk(info)
    return entries


def _entry_thumbnail(node: dict) -> str:
    """Обложка элемента выдачи: полем или последним (крупнейшим) из вариантов."""
    thumb = node.get("thumbnail")
    if not thumb:
        variants = node.get("thumbnails") or []
        thumb = variants[-1].get("url") if variants else ""
    return str(thumb or "")


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


def search_videos(query: str, limit: int = 1, sleep_requests: int = 1) -> list[VideoEntry]:
    """Результаты поиска YouTube по свободному запросу, до limit штук."""
    opts = {
        **_base_opts(sleep_requests=sleep_requests),
        "extract_flat": "in_playlist",
        "skip_download": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"ytsearch{max(1, limit)}:{query}", download=False)
    return _collect_entries(info)


# Фильтр «Songs» в поиске YouTube Music. Без него выдача мешает альбомы,
# плейлисты и видео, и половина записей приходит без пригодного video_id.
_YTM_SONGS_FILTER = "EgWKAQIIAWoKEAoQCRADEAQQBQ%3D%3D"


def search_music_titles(query: str, limit: int = 20) -> list[str]:
    """Названия треков из YouTube Music — чистая дискография артиста.

    Идея подсмотрена у Lavalink-ботов: у них есть отдельный префикс поиска
    `ytmsearch:`. Разница принципиальная — обычный YouTube это видеохостинг, и
    на «big baby tape» он отдаёт клипы, реакции и часовые миксы, а YouTube Music
    это каталог лейблов: только треки, только официальные поставки.

    Возвращаем именно НАЗВАНИЯ, а не кандидатов: в быстром режиме YT Music не
    отдаёт ни длительность, ни исполнителя, а качать каждую запись отдельно ради
    метаданных дорого. Названия нужны прогреву — он ищет по ним в SoundCloud,
    где есть и метаданные, и готовый mp3 без перекодирования.
    """
    url = f"https://music.youtube.com/search?q={quote(query)}&sp={_YTM_SONGS_FILTER}"
    opts = {
        **_base_opts(sleep_requests=0),
        "extract_flat": "in_playlist",
        "skip_download": True,
        "playlistend": max(1, limit),
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception:  # noqa: BLE001 — YouTube мог ответить антиботом
        logger.warning("YouTube Music: поиск «%s» не удался", query, exc_info=True)
        return []
    titles = [
        (entry.get("title") or "").strip()
        for entry in ((info or {}).get("entries") or [])
        if entry.get("title")
    ]
    return titles[:limit]


def search_first_video(query: str) -> VideoEntry | None:
    """Первый результат поиска YouTube по запросу «исполнитель название».
    Нужен переносу плейлистов: чужие сервисы отдают только метаданные."""
    entries = search_videos(query, limit=1)
    return entries[0] if entries else None


def download_audio(video_id: str, as_mp3: bool = False) -> DownloadedAudio | None:
    """as_mp3=True — гарантированно mp3 (перекодирование ffmpeg): поисковый парсер
    отдаёт пользователю mp3. Массовая закачка зовёт без флага (bestaudio)."""
    from app.services.disk import enough_free_disk

    if not enough_free_disk():
        return None  # диск почти полон — не забиваем /tmp, бережём Redis/бота
    with tempfile.TemporaryDirectory() as tmp:
        opts = {
            **_base_opts(),
            "format": settings.youtube_audio_format,
            "outtmpl": str(Path(tmp) / "%(id)s.%(ext)s"),
            "noplaylist": True,
            "retries": settings.youtube_max_retries,
        }
        if as_mp3:
            opts["postprocessors"] = [
                {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}
            ]
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

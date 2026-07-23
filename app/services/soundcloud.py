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
from urllib.parse import parse_qs, urlsplit

import yt_dlp

from app.config import settings
from app.services.youtube.downloader import DownloadedAudio, _base_opts, _read_supported

logger = logging.getLogger(__name__)

_SOUNDCLOUD_RE = re.compile(r"(?:https?://)?(?:www\.|m\.|on\.)?soundcloud\.com/\S+")

# Псевдо-вкладки веб-интерфейса SoundCloud без API-эндпоинта: yt-dlp отдаёт 404.
# Их сворачиваем к корню профиля — оттуда достаются все треки автора.
# А /tracks, /likes, /reposts, /sets, /albums yt-dlp открывает напрямую — НЕ трогаем,
# чтобы «скачать лайки» качало именно лайки, а не треки профиля.
_BROKEN_TABS = {"popular-tracks", "top-tracks"}


@dataclass(frozen=True)
class SoundcloudEntry:
    url: str
    title: str


def is_soundcloud_link(text: str) -> bool:
    return bool(_SOUNDCLOUD_RE.search(text or ""))


def _search_query(path: str, query: str) -> str | None:
    """Возвращает поисковый запрос, если это страница поиска или тега SoundCloud.
    Такие страницы не имеют API-URL — переводим их в scsearch."""
    first = path.split("/", 1)[0]
    if first == "search":
        q = parse_qs(query).get("q", [""])[0].strip()
        return q or None
    if first == "tags":
        tag = path.split("/", 1)[1] if "/" in path else ""
        return tag.replace("-", " ").strip() or None
    return None


def normalize_soundcloud_url(url: str) -> str:
    """Приводит любую страницу SoundCloud к тому, что понимает yt-dlp:
    - страница поиска/тега → `scsearch<N>:запрос` (у них нет API-URL);
    - псевдо-вкладка /popular-tracks → корень профиля (иначе 404);
    - трек/профиль/лайки/сеты/плейлист — как есть."""
    if url.startswith("scsearch"):  # уже нормализованный поисковый запрос — идемпотентно
        return url
    split = urlsplit(url if url.startswith("http") else f"https://{url}")
    path = split.path.strip("/")

    search = _search_query(path, split.query)
    if search:
        return f"scsearch{settings.soundcloud_search_limit}:{search}"

    clean = f"https://soundcloud.com/{path}"
    parts = path.split("/")
    if len(parts) == 2 and parts[1] in _BROKEN_TABS:
        return f"https://soundcloud.com/{parts[0]}"
    return clean


# Вкладки/разделы профиля — это всегда «много треков» (пачка).
_LISTING_SEGMENTS = {
    "popular-tracks",
    "top-tracks",
    "tracks",
    "reposts",
    "likes",
    "albums",
    "sets",
    "comments",
    "following",
    "followers",
}


def soundcloud_link_kind(url: str) -> str | None:
    """'track' — одиночный трек (бесплатно), 'bulk' — профиль/лайки/сет/поиск/тег
    (пачка, только Premium), None — не ссылка SoundCloud."""
    if not is_soundcloud_link(url):
        return None
    split = urlsplit(url if url.startswith("http") else f"https://{url}")
    parts = [p for p in split.path.split("/") if p]
    if not parts or parts[0] in ("search", "tags", "discover"):
        return "bulk"  # профиль целиком / поиск / тег
    if len(parts) == 2 and parts[1] not in _LISTING_SEGMENTS:
        return "track"  # soundcloud.com/user/track-name
    return "bulk"  # /user/likes, /user/sets/name и т.п.


def extract_soundcloud_url(text: str) -> str | None:
    match = _SOUNDCLOUD_RE.search(text or "")
    if not match:
        return None
    url = match.group(0)
    if not url.startswith("http"):
        url = f"https://{url}"
    return normalize_soundcloud_url(url)


def _proxy_attempts() -> int:
    """Сколько раз пробовать через разные прокси. Без прокси — одна попытка."""
    return max(1, min(len(settings.proxy_list_items), 3))


def list_soundcloud_entries(url: str) -> list[SoundcloudEntry]:
    """Трек → один элемент; профиль/сет → список треков (без скачивания).
    Нормализуем URL и здесь — чинит уже сохранённые источники с вкладкой-суффиксом.
    При ошибке через прокси — повтор через следующий (ротация в _base_opts)."""
    last_error: Exception | None = None
    for attempt in range(_proxy_attempts()):
        opts = {
            **_base_opts(impersonate=True, use_proxy=True),
            "extract_flat": "in_playlist",
            "skip_download": True,
        }
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(normalize_soundcloud_url(url), download=False)
        except Exception as exc:  # noqa: BLE001 — сеть/прокси, пробуем следующий
            last_error = exc
            logger.warning("SoundCloud: список не получен (попытка %s): %s", attempt + 1, exc)
            continue
        if info is None:
            return []
        return collect_soundcloud_entries(info)
    raise last_error if last_error else RuntimeError(f"SoundCloud: список не получен {url}")


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
    """Скачивает один трек. Возвращает (аудио, uploader) или None.
    Ошибка сети/прокси → повтор через следующий прокси; последняя ошибка наружу
    (вызывающая сторона различает постоянные отказы по тексту)."""
    last_error: Exception | None = None
    for attempt in range(_proxy_attempts()):
        try:
            return _download_soundcloud_once(url)
        except Exception as exc:  # noqa: BLE001 — сеть/прокси, пробуем следующий
            last_error = exc
            logger.warning("SoundCloud: скачивание %s (попытка %s): %s", url, attempt + 1, exc)
    raise last_error if last_error else RuntimeError(f"SoundCloud: не скачался {url}")


def _download_soundcloud_once(url: str) -> tuple[DownloadedAudio, str] | None:
    with tempfile.TemporaryDirectory() as tmp:
        opts = {
            **_base_opts(impersonate=True, use_proxy=True),
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
            thumbnail_url=str(info.get("thumbnail") or ""),
            album=str(info.get("album") or "").strip(),
        )
        return audio, (info.get("uploader") or "").strip()

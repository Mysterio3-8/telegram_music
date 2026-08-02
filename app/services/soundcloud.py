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

# yt-dlp часто отдаёт превью SoundCloud в размере -large (100×100) — на пол-экрана
# в плеере это мыло. Апскейлим к t500x500 (тот же CDN, просто другой суффикс).
_SC_ARTWORK_SIZE_RE = re.compile(r"-(?:large|t\d+x\d+|small|tiny|badge|mini)(\.\w+)$")


def upscale_soundcloud_artwork(url: str) -> str:
    if not url or "sndcdn.com" not in url:
        return url
    return _SC_ARTWORK_SIZE_RE.sub(r"-t500x500\1", url)


def fetch_cover_url(query: str) -> str | None:
    """Обложка первого результата SoundCloud по запросу «Исполнитель Название» —
    без скачивания аудио (только метаданные). Для восстановления обложек треков,
    залитых без картинки. None — не нашли."""
    opts = {**_base_opts(impersonate=True, use_proxy=True), "skip_download": True, "extract_flat": False}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f"scsearch1:{query}", download=False)
    except Exception:  # noqa: BLE001 — источник мог отвалиться
        return None
    entries = (info or {}).get("entries") or []
    if not entries or not entries[0]:
        return None
    thumb = entries[0].get("thumbnail") or ""
    return upscale_soundcloud_artwork(thumb) or None


@dataclass(frozen=True)
class SoundcloudEntry:
    url: str
    title: str
    # Длительность из выдачи (extract_flat отдаёт её для SoundCloud). 0 — неизвестна.
    # Поисковый парсер отсекает по ней мусор ДО скачивания — это и даёт «за секунды».
    duration: int = 0
    # Автор загрузки: отличает официальный аплоад артиста от чужого реаплоада —
    # поиск «kizaru …» не должен отдавать кавер от «кизяка».
    uploader: str = ""
    # Обложка из выдачи: живой поиск рисует карточки до скачивания
    cover_url: str = ""


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


def attempt_plan() -> list[bool]:
    """Порядок попыток: сначала прокси (ротация в _base_opts), в конце —
    ОБЯЗАТЕЛЬНО прямое соединение.

    Прямая попытка добавлена после прода 2026-08-02: все семь прокси в пуле
    отвечали Connection refused, и SoundCloud — приоритетный источник поиска —
    молча отдавал ноль результатов месяцами. Мёртвый пул прокси не должен
    выключать источник целиком; напрямую SoundCloud отвечает нормально.
    """
    if not settings.proxy_list_items:
        return [False]
    return [True] * _proxy_attempts() + [False]


def list_soundcloud_entries(url: str) -> list[SoundcloudEntry]:
    """Трек → один элемент; профиль/сет → список треков (без скачивания).
    Нормализуем URL и здесь — чинит уже сохранённые источники с вкладкой-суффиксом.
    Ошибка попытки — переходим к следующей, последняя всегда без прокси."""
    last_error: Exception | None = None
    for attempt, use_proxy in enumerate(attempt_plan(), start=1):
        opts = {
            **_base_opts(impersonate=True, use_proxy=use_proxy),
            "extract_flat": "in_playlist",
            "skip_download": True,
        }
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(normalize_soundcloud_url(url), download=False)
        except Exception as exc:  # noqa: BLE001 — сеть/прокси, пробуем следующую попытку
            last_error = exc
            logger.warning("SoundCloud: список не получен (попытка %s): %s", attempt, exc)
            continue
        if info is None:
            # yt-dlp гасит ошибку сам и отдаёт None — это отказ, а не пустая выдача.
            # Раньше здесь стоял return [], и мёртвый прокси выглядел как «ничего
            # не найдено»: ротация не срабатывала вообще.
            logger.warning("SoundCloud: пустой ответ (попытка %s)", attempt)
            continue
        return collect_soundcloud_entries(info)
    raise last_error if last_error else RuntimeError(f"SoundCloud: список не получен {url}")


def entry_thumbnail(node: dict) -> str:
    """Обложка элемента выдачи. extract_flat отдаёт её то полем, то списком
    вариантов — берём последний (самый крупный) и апскейлим до t500x500."""
    thumb = node.get("thumbnail")
    if not thumb:
        variants = node.get("thumbnails") or []
        thumb = variants[-1].get("url") if variants else ""
    return upscale_soundcloud_artwork(str(thumb or ""))


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
            entries.append(
                SoundcloudEntry(
                    entry_url,
                    node.get("title") or entry_url,
                    duration=int(node.get("duration") or 0),
                    uploader=str(node.get("uploader") or node.get("channel") or "").strip(),
                    cover_url=entry_thumbnail(node),
                )
            )

    walk(info)
    return entries


def download_soundcloud_audio(url: str, as_mp3: bool = False) -> tuple[DownloadedAudio, str] | None:
    """Скачивает один трек. Возвращает (аудио, uploader) или None.
    as_mp3=True — гарантированный mp3 (перекодирование ffmpeg): поисковый парсер
    отдаёт пользователю только mp3. Массовая закачка 24/7 зовёт без флага —
    там перекодировать каждый трек дорого, храним исходный контейнер.
    Ошибка сети/прокси → повтор через следующий прокси; последняя ошибка наружу
    (вызывающая сторона различает постоянные отказы по тексту)."""
    from app.services.disk import enough_free_disk

    if not enough_free_disk():
        return None  # диск почти полон — 24/7-парсер не забивает диск (бережём бота)
    last_error: Exception | None = None
    for attempt, use_proxy in enumerate(attempt_plan(), start=1):
        try:
            result = _download_soundcloud_once(url, as_mp3=as_mp3, use_proxy=use_proxy)
        except Exception as exc:  # noqa: BLE001 — сеть/прокси, пробуем следующую попытку
            last_error = exc
            logger.warning("SoundCloud: скачивание %s (попытка %s): %s", url, attempt, exc)
            continue
        if result is not None:
            return result
        logger.warning("SoundCloud: пустой ответ на скачивании (попытка %s)", attempt)
    if last_error:
        raise last_error
    return None  # источник ответил, но трека нет — это не сбой сети


def _download_soundcloud_once(
    url: str, as_mp3: bool = False, use_proxy: bool = True
) -> tuple[DownloadedAudio, str] | None:
    with tempfile.TemporaryDirectory() as tmp:
        opts = {
            **_base_opts(impersonate=True, use_proxy=use_proxy),
            # mp3 предпочтительнее «на входе»: если источник уже отдаёт mp3,
            # перекодирование не понадобится вовсе (быстрее и без потери качества)
            "format": "bestaudio[ext=mp3]/bestaudio/best",
            "outtmpl": str(Path(tmp) / "sc.%(ext)s"),
            "noplaylist": True,
            "retries": settings.youtube_max_retries,
        }
        if as_mp3:
            opts["postprocessors"] = [
                {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}
            ]
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
            thumbnail_url=upscale_soundcloud_artwork(str(info.get("thumbnail") or "")),
            album=str(info.get("album") or "").strip(),
        )
        return audio, (info.get("uploader") or "").strip()

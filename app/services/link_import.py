"""Импорт трека по ссылке с ЛЮБОЙ площадки, которую понимает yt-dlp.

Раньше бот принимал только YouTube и SoundCloud, и ссылка с Bandcamp, VK,
Mixcloud, Audiomack, Vimeo или личного сайта артиста получала ответ «жду файл
или ссылку» — то есть выглядела как поломка, хотя yt-dlp такие площадки
поддерживает больше тысячи.

У специализированных путей (YouTube, SoundCloud) остаётся приоритет: там мы
умеем больше — знаем, как разбирать заголовок, откуда брать обложку и автора,
как считать дубликаты по ссылке источника. Этот модуль — про всё остальное.

🔴 **Чего он НЕ делает и делать не будет.** Spotify, Apple Music, Deezer, Tidal
и Яндекс.Музыка отдают только зашифрованный поток: файла там нет ни у нас, ни у
yt-dlp. Обойти это — снять техническую защиту, чего мы не делаем. Зато список
треков с них читается, и «Перенос из других сервисов» находит те же песни в
доступных источниках. Поэтому такие ссылки не падают с ошибкой, а отправляются
туда, где они работают.
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

_URL_RE = re.compile(r"https?://\S+")

# Площадки с DRM: скачать нечего, но перенос по названиям работает.
# Ключ — кусок домена, значение — как называть сервис человеку.
DRM_SERVICES: dict[str, str] = {
    "open.spotify.com": "Spotify",
    "spotify.link": "Spotify",
    "music.apple.com": "Apple Music",
    "music.yandex.": "Яндекс.Музыка",
    "deezer.com": "Deezer",
    "tidal.com": "Tidal",
    "music.amazon.": "Amazon Music",
}


@dataclass(frozen=True)
class LinkEntry:
    url: str
    title: str


def extract_url(text: str) -> str | None:
    match = _URL_RE.search(text or "")
    return match.group(0).rstrip(".,;)") if match else None


def drm_service_name(url: str) -> str | None:
    """«Spotify» / «Apple Music» / … — если ссылка на площадку с DRM. Иначе None."""
    text = (url or "").lower()
    for marker, name in DRM_SERVICES.items():
        if marker in text:
            return name
    return None


def looks_like_bulk(url: str) -> bool:
    """Похоже ли на плейлист/профиль/альбом, а не на один трек.

    Смотрим на форму ссылки, а не спрашиваем сеть: разбор через yt-dlp это
    секунды ожидания, а решение «пачка или нет» нужно до того, как человеку
    ответить. Ошибиться не страшно — скачивание всё равно разберётся.
    """
    text = (url or "").lower()
    markers = ("/playlist", "/album", "/sets/", "list=", "/channel/", "/user/", "/artist")
    return any(marker in text for marker in markers)


def download_any(url: str) -> tuple[DownloadedAudio, str] | None:
    """Скачивает трек с произвольной площадки. None — источнику нечего отдать.

    Всегда приводим к mp3: площадок больше тысячи, контейнеры у них какие
    угодно, а в плеере Telegram играют только mp3 и m4a — без приведения часть
    треков приходила бы молчаливым вложением.
    """
    from app.services.disk import enough_free_disk

    if not enough_free_disk():
        return None
    with tempfile.TemporaryDirectory() as tmp:
        opts = {
            **_base_opts(),
            "format": "bestaudio/best",
            "outtmpl": str(Path(tmp) / "link.%(ext)s"),
            "noplaylist": True,  # ссылка на трек внутри плейлиста — берём трек
            "retries": settings.youtube_max_retries,
            "max_filesize": settings.max_file_size_mb * 1024 * 1024,
            "postprocessors": [
                {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}
            ],
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
        if info is None:
            return None
        files = [p for p in Path(tmp).glob("link.*") if not p.name.endswith(".conv.m4a")]
        if not files:
            return None
        data, file_format = _read_supported(files[0])
        # У разных площадок автор лежит в разных полях; порядок — по убыванию
        # доверия: явный artist из метаданных, затем аплоадер, затем канал.
        uploader = str(
            info.get("artist") or info.get("uploader") or info.get("channel") or ""
        ).strip()
        audio = DownloadedAudio(
            data=data,
            file_format=file_format,
            duration=int(info.get("duration") or 0),
            video_title=info.get("track") or info.get("title") or url,
            uploader=uploader,
            thumbnail_url=str(info.get("thumbnail") or ""),
            album=str(info.get("album") or "").strip(),
        )
        return audio, uploader


def list_any_entries(url: str) -> list[LinkEntry]:
    """Треки плейлиста/профиля без скачивания. Пустой список — не разобрали."""
    opts = {**_base_opts(), "extract_flat": "in_playlist", "skip_download": True}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception:  # noqa: BLE001 — площадка недоступна/закрыта
        logger.warning("Ссылка: не удалось прочитать %s", url, exc_info=True)
        return []
    return collect_entries(info or {})


def collect_entries(info: dict) -> list[LinkEntry]:
    """Чистый разбор ответа yt-dlp — отделён от сети ради тестов."""
    found: list[LinkEntry] = []
    seen: set[str] = set()

    def walk(node) -> None:
        if not isinstance(node, dict):
            return
        if node.get("entries") is not None:
            for child in node["entries"]:
                walk(child)
            return
        entry_url = node.get("url") or node.get("webpage_url")
        if entry_url and entry_url not in seen:
            seen.add(entry_url)
            found.append(LinkEntry(entry_url, node.get("title") or entry_url))

    walk(info)
    return found


async def process_user_link_import(session, bot, url: str, telegram_id: int) -> tuple:
    """Ссылка от пользователя → трек в общей базе и в его библиотеке.

    Зеркало `process_user_soundcloud_import`, но для произвольной площадки: там,
    где источник специализированный, работает свой путь с лучшими метаданными.
    """
    from app.services.youtube.user_import import UserImportRejected, import_downloaded_audio

    result = download_any(url)
    if result is None:
        raise UserImportRejected(
            "С этой ссылки скачать не вышло — площадка не отдала файл."
        )
    audio, _ = result
    # Общий хвост импорта: фильтры длительности и размера, минт, библиотека,
    # счётчик загрузок. Дубликат ловим по ссылке источника — она у нас есть.
    return await import_downloaded_audio(session, bot, audio, telegram_id, source_url=url)

"""Поисковый парсер #2 (решение владельца): ищет трек ОТОВСЮДУ по свободному
запросу и качает mp3. Спрятан — в интерфейсе не показывается.

Пользователь пишет как угодно (транслит, кириллица, опечатки, любой язык) →
пробуем источники по очереди через yt-dlp, берём первый результат, качаем.
Порядок: SoundCloud (чистый mp3, наш основной каталог) → YouTube (фолбэк, шире
покрытие). VK/Яндекс отдаются с DRM — не качаются, покрыты переносом плейлистов.
"""
import logging
import re
import tempfile
from pathlib import Path

import yt_dlp

from app.config import settings
from app.services.youtube.downloader import DownloadedAudio, _base_opts, _read_supported

logger = logging.getLogger(__name__)

_WHITESPACE_RE = re.compile(r"\s+")


def clean_query(text: str) -> str:
    """Нормализует свободный запрос: обрезка, схлопывание пробелов."""
    return _WHITESPACE_RE.sub(" ", (text or "").strip())


def build_search_specs(query: str) -> list[str]:
    """yt-dlp search-спеки по источникам в порядке приоритета. Пустой запрос → []."""
    q = clean_query(query)
    if not q:
        return []
    # SoundCloud первым: чистый mp3 и наш основной источник; YouTube — фолбэк-покрытие
    return [f"scsearch1:{q}", f"ytsearch1:{q}"]


def _is_soundcloud_spec(spec: str) -> bool:
    return spec.startswith("scsearch")


def _download_spec(spec: str) -> tuple[DownloadedAudio, str] | None:
    """Скачивает первый результат поиска по спеку. None — ничего не найдено."""
    with tempfile.TemporaryDirectory() as tmp:
        is_sc = _is_soundcloud_spec(spec)
        opts = {
            **_base_opts(impersonate=is_sc, use_proxy=is_sc),
            # mp3, если источник его отдаёт (SoundCloud часто), иначе лучший звук
            "format": "bestaudio[ext=mp3]/bestaudio/best",
            "outtmpl": str(Path(tmp) / "hit.%(ext)s"),
            "noplaylist": True,
            "retries": settings.youtube_max_retries,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(spec, download=True)
        entry = _first_entry(info)
        if entry is None:
            return None
        files = [p for p in Path(tmp).glob("hit.*") if not p.name.endswith(".conv.m4a")]
        if not files:
            return None
        data, file_format = _read_supported(files[0])
        uploader = (
            entry.get("artist")
            or entry.get("creator")
            or entry.get("uploader")
            or entry.get("channel")
            or ""
        )
        audio = DownloadedAudio(
            data=data,
            file_format=file_format,
            duration=int(entry.get("duration") or 0),
            video_title=entry.get("title") or clean_query(spec.split(":", 1)[-1]),
            uploader=str(uploader).strip(),
            thumbnail_url=str(entry.get("thumbnail") or ""),
            album=str(entry.get("album") or "").strip(),
        )
        return audio, str(uploader).strip()


def _first_entry(info: dict | None) -> dict | None:
    """Search-ответ yt-dlp оборачивает результаты в entries; берём первый непустой."""
    if info is None:
        return None
    entries = info.get("entries")
    if entries is None:
        return info
    for entry in entries:
        if entry:
            return entry
    return None


def search_and_download(query: str) -> tuple[DownloadedAudio, str] | None:
    """Проходит источники по приоритету, возвращает первый скачанный трек.
    None — не нашли нигде. Сетевые ошибки одного источника не роняют остальные."""
    for spec in build_search_specs(query):
        try:
            result = _download_spec(spec)
        except Exception as exc:  # noqa: BLE001 — источник недоступен, пробуем следующий
            logger.warning("Поисковый парсер: %s не дал результат: %s", spec, exc)
            continue
        if result is not None:
            logger.info("Поисковый парсер: «%s» найден через %s", query, spec.split(":", 1)[0])
            return result
    return None


async def fetch_track_by_query(session, bot, query: str, telegram_id: int):
    """Спрятанный поисковый парсер end-to-end: находит трек отовсюду, минтит в общую
    базу и кладёт в библиотеку пользователя. Возвращает (Track, created) | None.

    Импортируется лениво внутри функции: тяжёлые зависимости (aiogram/минт) не нужны
    для юнит-тестов чистого разбора запроса."""
    from app.services.catalog_import import import_via_telegram_mint
    from app.services.fingerprint import compute_fingerprint_from_bytes
    from app.services.library import add_to_library
    from app.services.title_parser import parse_title
    from app.services.users import get_user_by_telegram_id
    from app.services.youtube.downloader import fetch_thumbnail

    user = await get_user_by_telegram_id(session, telegram_id)
    if user is None:
        return None

    found = search_and_download(query)
    if found is None:
        return None
    audio, uploader = found

    fallback_artist = uploader.removesuffix(" - Topic").strip() or "Исполнитель"
    artist, title = parse_title(audio.video_title, fallback_artist)
    fingerprint = compute_fingerprint_from_bytes(audio.data, suffix=f".{audio.file_format}")

    track, created = await import_via_telegram_mint(
        session,
        bot,
        title=title,
        artist=artist,
        duration=audio.duration,
        file_format=audio.file_format,
        data=audio.data,
        fingerprint=fingerprint,
        archive_chat_id=settings.effective_archive_chat_id,
        cover=fetch_thumbnail(audio.thumbnail_url),
        cover_url=audio.thumbnail_url or None,
        album=audio.album or None,
    )
    await add_to_library(session, user.id, track.id)
    return track, created

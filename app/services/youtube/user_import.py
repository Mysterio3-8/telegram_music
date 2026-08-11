"""Пользовательский импорт трека по YouTube-ссылке (доп. ТЗ: парсер в общий доступ).

Ограничения против мусора (бот музыкальный, видео/подкасты не нужны):
- только одиночное видео, не прямой эфир;
- длительность в границах settings.track_min_seconds..track_max_seconds
  (проверяется дважды: по метаданным ДО скачивания и по факту после);
- лимит бесплатного тарифа — тот же, что у загрузки файлом (can_upload);
- дедуп по отпечатку/метаданным — как у остальных импортёров.
"""
import asyncio
import logging
import re

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import Track, Upload, User
from app.services.catalog_import import import_via_telegram_mint
from app.services.fingerprint import compute_fingerprint_from_bytes
from app.services.library import add_to_library
from app.services.title_parser import parse_title
from app.services.youtube.downloader import (
    DownloadedAudio,
    download_audio,
    fetch_telegram_thumbnail,
    fetch_thumbnail,
)

logger = logging.getLogger(__name__)


async def _none():
    """Заглушка вместо задачи отпечатка, когда он не нужен: gather ждёт корутину."""
    return None

# youtu.be/ID | youtube.com/watch?v=ID | youtube.com/shorts/ID | music.youtube.com/watch?v=ID
_URL_PATTERNS = [
    re.compile(r"youtu\.be/([A-Za-z0-9_-]{11})"),
    re.compile(r"youtube\.com/(?:watch\?(?:[^ ]*&)?v=|shorts/|embed/|live/)([A-Za-z0-9_-]{11})"),
]


_PLAYLIST_PATTERNS = [
    re.compile(r"youtube\.com/playlist\?"),
    re.compile(r"[?&]list="),
    re.compile(r"youtube\.com/(?:@[\w.-]+|channel/|c/|user/)"),
]


def extract_video_id(text: str) -> str | None:
    """Достаёт video_id из YouTube-ссылки. None — это не ссылка на видео."""
    for pattern in _URL_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(1)
    return None


def is_playlist_link(text: str) -> bool:
    """Ссылка на плейлист или канал целиком (импорт пачкой, только Premium)."""
    if "youtu" not in text:
        return False
    return any(p.search(text) for p in _PLAYLIST_PATTERNS)


def duration_error(seconds: int) -> str | None:
    """None — длительность в допустимых границах; иначе текст отказа для пользователя.
    Границы 0 в конфиге означают «лимит снят» — соответствующая проверка пропускается."""
    if settings.track_min_seconds and seconds < settings.track_min_seconds:
        return (
            f"Слишком короткое ({seconds} сек). "
            f"Принимаем треки от {settings.track_min_seconds} секунд."
        )
    if settings.track_max_seconds and seconds > settings.track_max_seconds:
        return (
            f"Слишком длинное ({seconds // 60} мин). Похоже на видео или подкаст — "
            f"принимаем музыку до {settings.track_max_seconds // 60} минут."
        )
    return None


class UserImportRejected(Exception):
    """Контент не прошёл фильтры — НЕ повторять задачу, сообщить пользователю."""


async def import_downloaded_audio(
    session: AsyncSession,
    bot: Bot,
    audio: DownloadedAudio,
    telegram_id: int,
    save_to_library: bool = True,
    source_url: str | None = None,
    with_fingerprint: bool = True,
) -> tuple[Track, bool]:
    """Общий хвост импорта: фильтры, запись в общую базу, библиотека, лимит загрузок.

    save_to_library=False — «просто пришли послушать»: трек попадает в общий
    каталог, но НЕ в личную библиотеку. Раньше библиотека пополнялась всегда, и
    человек, попросивший один трек из выдачи, молча получал его себе в коллекцию.

    Одинаков для импорта по ссылке и по поисковому запросу — источник роли не играет,
    на вход приходит уже скачанное аудио.
    """
    from app.services.users import get_user_by_telegram_id

    user = await get_user_by_telegram_id(session, telegram_id)
    if user is None:
        raise UserImportRejected("Пользователь не найден — отправьте /start")

    # Повторная проверка по факту: метаданные могли соврать
    error = duration_error(audio.duration)
    if error:
        raise UserImportRejected(error)
    if len(audio.data) > settings.max_file_size_mb * 1024 * 1024:
        raise UserImportRejected(f"Файл больше {settings.max_file_size_mb} МБ.")

    # YouTube Music помечает авто-каналы «Исполнитель - Topic» — чистим суффикс
    fallback_artist = audio.uploader.removesuffix(" - Topic").strip() or "Исполнитель"
    artist, title = parse_title(audio.video_title, fallback_artist)

    # Три блокирующие операции разом: отпечаток (fpcalc декодирует трек целиком),
    # обложка и миниатюра под Telegram (два похода в сеть по 15 сек таймаута).
    # Раньше они шли подряд прямо в событийном цикле — это и держало человека в
    # ожидании, пока трек «качается». Теперь параллельно и в потоках.
    fingerprint_task = (
        asyncio.to_thread(
            compute_fingerprint_from_bytes, audio.data, suffix=f".{audio.file_format}"
        )
        if with_fingerprint
        else _none()
    )
    fingerprint, cover, thumbnail = await asyncio.gather(
        fingerprint_task,
        asyncio.to_thread(fetch_thumbnail, audio.thumbnail_url),
        asyncio.to_thread(fetch_telegram_thumbnail, audio.thumbnail_url),
    )

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
        cover=cover,
        cover_url=audio.thumbnail_url or None,
        album=audio.album or None,
        thumbnail=thumbnail,
        source_url=source_url,
    )

    if created:
        # Считаем в лимит загрузок пользователя — как загрузку файлом
        session.add(Upload(user_id=user.id, track_id=track.id))
        await session.commit()
    if save_to_library:
        await add_to_library(session, user.id, track.id)
    return track, created


async def process_user_import(
    session: AsyncSession, bot: Bot, video_id: str, telegram_id: int
) -> tuple[Track, bool]:
    """Скачивает и заводит трек от имени пользователя. Возвращает (трек, создан_ли).
    Кидает UserImportRejected при нарушении фильтров (без повторов)."""
    audio = download_audio(video_id)
    if audio is None:
        raise RuntimeError(f"yt-dlp не вернул аудио для {video_id}")

    track, created = await import_downloaded_audio(session, bot, audio, telegram_id)
    logger.info(
        "Импорт по ссылке video=%s user=%s → track=%s (created=%s)",
        video_id, telegram_id, track.id, created,
    )
    return track, created

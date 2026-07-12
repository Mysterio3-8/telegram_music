"""Импорт одного аудиопоста канала — без постоянного хранения файла на диске.

Байты скачиваются во временную память ровно на время обработки: посчитать
отпечаток и перезалить через бота (чтобы получить свой tg_file_id). Сразу
после этого ссылка на bytes отбрасывается — на сервере ничего не остаётся.
"""
import logging
from datetime import datetime, timezone

from aiogram import Bot
from aiogram.types import BufferedInputFile
from sqlalchemy.ext.asyncio import AsyncSession
from telethon import TelegramClient

from app.config import settings
from app.db.models import TelegramChannelImport, TelegramChannelSource
from app.services.catalog_import import create_track_from_telegram, find_existing_track
from app.services.fingerprint import compute_fingerprint_from_bytes
from app.services.title_parser import parse_title
from app.services.track_meta import build_filename, retag_audio

logger = logging.getLogger(__name__)


class ImportError_(Exception):
    """Временная ошибка импорта — задача должна быть повторена."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def process_import(
    session: AsyncSession, bot: Bot, client: TelegramClient, import_id: int
) -> str:
    """Обрабатывает одну задачу. Возвращает финальный статус (imported/skipped).
    Кидает исключение при временной ошибке — воркер повторит попытку."""
    imp = await session.get(TelegramChannelImport, import_id)
    if imp is None:
        return "skipped"
    if imp.status == "imported":
        return "imported"
    source = await session.get(TelegramChannelSource, imp.source_id)
    if source is None:
        return "skipped"
    fallback_artist = source.title or "Unknown"

    imp.status = "downloading"
    imp.attempts += 1
    await session.commit()

    entity = await client.get_entity(source.channel)
    message = await client.get_messages(entity, ids=imp.message_id)
    if message is None or not message.audio:
        raise ImportError_(f"Сообщение {imp.message_id} недоступно или уже без аудио")

    data = await client.download_media(message)  # bytes — в память, не на диск
    if not data:
        raise ImportError_(f"Пустое содержимое сообщения {imp.message_id}")

    imp.status = "processing"
    await session.commit()

    file = message.file
    posted_title = getattr(file, "title", None)
    posted_performer = getattr(file, "performer", None)
    duration = int(getattr(file, "duration", None) or 0)
    file_format = (getattr(file, "ext", None) or ".mp3").lstrip(".").lower()

    if posted_title and posted_performer:
        artist, title = posted_performer.strip(), posted_title.strip()
    else:
        source_text = message.message or posted_title or f"track_{imp.message_id}"
        artist, title = parse_title(source_text, fallback_artist)

    fingerprint = compute_fingerprint_from_bytes(data, suffix=f".{file_format}")

    track = await find_existing_track(session, fingerprint, title, artist, duration)
    if track is None:
        tagged = retag_audio(data, file_format, title, artist)
        data = None  # исходные байты больше не нужны
        sent = await bot.send_audio(
            settings.effective_archive_chat_id,
            BufferedInputFile(tagged, filename=build_filename(artist, title, file_format)),
            title=title,
            performer=artist,
            duration=duration or None,
        )
        track = await create_track_from_telegram(
            session,
            title=title,
            artist=artist,
            duration=duration,
            file_format=file_format,
            file_size=len(tagged),
            fingerprint=fingerprint,
            tg_file_id=sent.audio.file_id,
        )
        tagged = None  # заминчено в Telegram — локальная копия больше не нужна
    else:
        data = None  # трек уже был — скачанные байты не понадобились

    imp.detected_title = title[:256]
    imp.detected_artist = artist[:256]
    imp.original_title = (posted_title or message.message or "")[:512]
    imp.track_id = track.id
    imp.status = "imported"
    imp.last_error = None
    imp.imported_at = _utcnow()
    await session.commit()
    logger.info(
        "Telegram-канал импорт message=%s → track=%s (%s — %s)",
        imp.message_id, track.id, artist, title,
    )
    return "imported"


async def mark_failed(session: AsyncSession, import_id: int, error: str) -> None:
    imp = await session.get(TelegramChannelImport, import_id)
    if imp is not None:
        imp.status = "failed"
        imp.last_error = error[:512]
        await session.commit()

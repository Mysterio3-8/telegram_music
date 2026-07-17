"""Импорт одного аудиопоста канала — без постоянного хранения файла на диске.

Байты скачиваются во временную память ровно на время обработки: посчитать
отпечаток и перезалить через бота (чтобы получить свой tg_file_id). Сразу
после этого ссылка на bytes отбрасывается — на сервере ничего не остаётся.
"""
import logging
from datetime import datetime, timezone

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession
from telethon import TelegramClient

from app.config import settings
from app.db.models import TelegramChannelImport, TelegramChannelSource
from app.services.catalog_import import (
    import_instrumental_via_telegram_mint,
    import_via_telegram_mint,
)
from app.services.fingerprint import compute_fingerprint_from_bytes
from app.services.title_parser import parse_title

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

    if source.target == "instrumentals":
        # Канал с минусами: аудио уходит в отдельную таблицу instrumentals (TZ §9)
        instrumental, _created = await import_instrumental_via_telegram_mint(
            session,
            bot,
            title=title,
            artist=artist,
            duration=duration,
            file_format=file_format,
            data=data,
            fingerprint=fingerprint,
            archive_chat_id=settings.effective_archive_chat_id,
            source="tg_channel",
        )
        imported_id = instrumental.id
        kind = "instrumental"
    else:
        track, _created = await import_via_telegram_mint(
            session,
            bot,
            title=title,
            artist=artist,
            duration=duration,
            file_format=file_format,
            data=data,
            fingerprint=fingerprint,
            archive_chat_id=settings.effective_archive_chat_id,
        )
        imp.track_id = track.id
        imported_id = track.id
        kind = "track"
    data = None  # заминчено (или дубликат) — локальная копия больше не нужна

    imp.detected_title = title[:256]
    imp.detected_artist = artist[:256]
    imp.original_title = (posted_title or message.message or "")[:512]
    imp.status = "imported"
    imp.last_error = None
    imp.imported_at = _utcnow()
    await session.commit()
    logger.info(
        "Telegram-канал импорт message=%s → %s=%s (%s — %s)",
        imp.message_id, kind, imported_id, artist, title,
    )
    return "imported"


async def mark_failed(session: AsyncSession, import_id: int, error: str) -> None:
    imp = await session.get(TelegramChannelImport, import_id)
    if imp is not None:
        imp.status = "failed"
        imp.last_error = error[:512]
        await session.commit()

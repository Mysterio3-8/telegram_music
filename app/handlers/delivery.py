"""Выдача аудиофайла трека. Без роутера — общий модуль для карточки, очереди и скачивания.

Гарантия актуальных метаданных (SPEC: доработки, п.1 и п.5): если название/исполнитель
менялись (meta_synced=False), файл скачивается, перетегируется (ID3) и переотправляется
с именем «Исполнитель — Название.ext»; полученный file_id кэшируется — дальше трек
уходит мгновенно и уже с правильными данными. Пользователь никогда не получает файл
со старым названием, кроме случая, когда байты недоступны (файл >20 МБ без архива).
"""
import io
import logging

from aiogram import Bot
from aiogram.types import BufferedInputFile, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Track, User
from app.services.stats import record_event
from app.services.track_meta import build_filename, retag_audio

logger = logging.getLogger(__name__)


async def _load_original_bytes(bot: Bot, track: Track) -> bytes | None:
    """Байты трека: архивное хранилище, иначе скачивание из Telegram (лимит getFile 20 МБ)."""
    if track.storage_path:
        try:
            from app.storage import get_storage

            return get_storage().load(f"tracks/{track.id}")
        except Exception:  # noqa: BLE001
            logger.warning("Архив недоступен track=%s", track.id, exc_info=True)
    if track.tg_file_id:
        try:
            buffer = io.BytesIO()
            await bot.download(track.tg_file_id, destination=buffer)
            return buffer.getvalue()
        except Exception:  # noqa: BLE001
            logger.warning("Не удалось скачать track=%s из Telegram", track.id, exc_info=True)
    return None


async def send_track_audio(
    bot: Bot,
    chat_id: int,
    session: AsyncSession,
    user: User,
    track: Track,
    reply_markup: InlineKeyboardMarkup | None = None,
    caption: str | None = None,
    event: str = "listen",
) -> Message | None:
    """Отправляет аудио трека в чат. None — файла нет совсем. Пишет событие статистики."""
    message: Message | None = None

    if track.tg_file_id and track.meta_synced:
        message = await bot.send_audio(
            chat_id, track.tg_file_id, caption=caption, reply_markup=reply_markup
        )
    else:
        data = await _load_original_bytes(bot, track)
        if data is not None:
            data = retag_audio(data, track.format, track.title, track.artist)
            audio_file = BufferedInputFile(
                data, filename=build_filename(track.artist, track.title, track.format)
            )
            message = await bot.send_audio(
                chat_id,
                audio_file,
                caption=caption,
                title=track.title,
                performer=track.artist,
                duration=track.duration or None,
                reply_markup=reply_markup,
            )
            if message.audio is not None:
                track.tg_file_id = message.audio.file_id
                track.meta_synced = True
                await session.commit()
        elif track.tg_file_id:
            # Байты недоступны (файл >20 МБ, архив пуст) — отдаём как есть, это лучше отказа
            message = await bot.send_audio(
                chat_id, track.tg_file_id, caption=caption, reply_markup=reply_markup
            )

    if message is not None:
        await record_event(session, user.id, track.id, event)
    return message

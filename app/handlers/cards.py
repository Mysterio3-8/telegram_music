"""Карточка трека — отдельное сообщение с плеером Telegram и кнопками действий
(SPEC: доработки, п.8). Без роутера — модуль общий для всех разделов.

Карточка не заменяет предыдущий экран: она отправляется новым сообщением,
«Назад» удаляет её, а список выше остаётся рабочим (SPEC: доработки, п.2).
"""
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import Track, User
from app.handlers.common import format_duration
from app.handlers.delivery import send_track_audio
from app.keyboards.track_card import track_card_keyboard


def is_admin(telegram_id: int) -> bool:
    return telegram_id in settings.admin_id_set


def build_track_card_text(track: Track) -> str:
    return (
        f"🎧 {track.title}\n\n"
        f"Исполнитель: {track.artist}\n"
        f"Длительность: {format_duration(track.duration)}"
    )


async def build_card_keyboard(message: Message, track: Track, ctx: str, in_library: bool, telegram_id: int):
    me = await message.bot.me()
    return track_card_keyboard(track, ctx, in_library, me.username, is_admin(telegram_id))


async def show_track_card(
    message: Message,
    session: AsyncSession,
    user: User,
    track: Track,
    ctx: str,
    in_library: bool,
) -> None:
    """Отправляет карточку-плеер новым сообщением; без файла — текстовый фолбэк."""
    keyboard = await build_card_keyboard(message, track, ctx, in_library, user.telegram_id)
    sent = await send_track_audio(
        message.bot, message.chat.id, session, user, track, reply_markup=keyboard
    )
    if sent is None:
        await message.answer(build_track_card_text(track), reply_markup=keyboard)

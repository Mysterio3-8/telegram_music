"""Карточка трека — отдельное сообщение с плеером Telegram и кнопками действий
(SPEC: доработки, п.8). Без роутера — модуль общий для всех разделов.

Карточка не заменяет предыдущий экран: она отправляется новым сообщением,
«Назад» удаляет её, а список выше остаётся рабочим (SPEC: доработки, п.2).
"""
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Track, User
from app.handlers.common import format_duration
from app.handlers.delivery import send_track_audio
from app.keyboards.track_card import track_card_keyboard


def build_track_card_text(track: Track) -> str:
    return (
        t("card.title", title=track.title) + "\n\n"
        + t("common.artist_line", artist=track.artist) + "\n"
        + t("common.duration_line", duration=format_duration(track.duration))
    )


async def build_card_keyboard(
    message: Message, track: Track, ctx: str, in_library: bool, telegram_id: int | None = None
):
    """telegram_id больше не нужен: единственной кнопкой, зависевшей от
    пользователя, была админская правка трека, убранная 14.08. Параметр
    оставлен, чтобы не переписывать пять мест вызова ради ничего."""
    me = await message.bot.me()
    return track_card_keyboard(track, ctx, in_library, me.username)


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

"""Построение и показ карточки трека. Без роутера — модуль общий для всех разделов."""
from aiogram.types import Message

from app.db.models import Track
from app.handlers.common import format_duration
from app.keyboards.track_card import track_card_keyboard


def build_track_card_text(track: Track) -> str:
    return (
        f"🎧 {track.title}\n\n"
        f"Исполнитель: {track.artist}\n"
        f"Длительность: {format_duration(track.duration)}"
    )


async def show_track_card(
    message: Message, track: Track, ctx: str, in_library: bool, edit: bool = True
) -> None:
    text = build_track_card_text(track)
    keyboard = track_card_keyboard(track, ctx, in_library)
    if edit:
        await message.edit_text(text, reply_markup=keyboard)
    else:
        await message.answer(text, reply_markup=keyboard)

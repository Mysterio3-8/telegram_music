"""Клавиатура выдачи быстрого поиска в боте (формат по скринам владельца):
кнопка на каждый трек «2:19 Артист - Название» + пагинация внизу.
"""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.db.models import Track

PAGE_SIZE = 10
_MAX_BUTTON_TEXT = 60  # Telegram обрежет длиннее — режем сами, чтобы не терять хвост смысла


def _duration_label(seconds: int) -> str:
    minutes, rest = divmod(max(0, seconds or 0), 60)
    return f"{minutes}:{rest:02d}"


def track_button_text(track: Track) -> str:
    """«2:19 kizaru - AFK» — время, исполнитель, название."""
    label = f"{_duration_label(track.duration)} {track.artist} - {track.title}"
    if len(label) <= _MAX_BUTTON_TEXT:
        return label
    return label[: _MAX_BUTTON_TEXT - 1] + "…"


def quick_search_keyboard(tracks: list[Track], page: int, total_pages: int) -> InlineKeyboardMarkup:
    """Список треков + строка пагинации. Стрелки показываются только там, где есть куда идти."""
    rows = [
        [InlineKeyboardButton(text=track_button_text(t), callback_data=f"qs:t:{t.id}")]
        for t in tracks
    ]

    nav: list[InlineKeyboardButton] = []
    if page > 1:
        nav.append(InlineKeyboardButton(text="«", callback_data=f"qs:p:{page - 1}"))
    nav.append(InlineKeyboardButton(text=f"{page} / {total_pages}", callback_data="qs:noop"))
    if page < total_pages:
        nav.append(InlineKeyboardButton(text="»", callback_data=f"qs:p:{page + 1}"))
    if len(nav) > 1:
        rows.append(nav)

    return InlineKeyboardMarkup(inline_keyboard=rows)

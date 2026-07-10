from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.config import settings
from app.db.models import Track


def _track_rows(
    tracks: list[Track], first_number: int, back_page: int
) -> list[list[InlineKeyboardButton]]:
    return [
        [
            InlineKeyboardButton(
                text=f"{number}. {track.artist} — {track.title}",
                callback_data=f"lib:track:{track.id}:{back_page}",
            )
        ]
        for number, track in enumerate(tracks, start=first_number)
    ]


def library_keyboard(tracks: list[Track], page: int, total_pages: int) -> InlineKeyboardMarkup:
    first_number = (page - 1) * settings.page_size + 1
    rows = _track_rows(tracks, first_number, back_page=page)

    nav: list[InlineKeyboardButton] = []
    if page > 1:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"lib:page:{page - 1}"))
    nav.append(InlineKeyboardButton(text=f"Страница {page} / {total_pages}", callback_data="noop"))
    if page < total_pages:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"lib:page:{page + 1}"))
    rows.append(nav)

    rows.append([InlineKeyboardButton(text="🔍 Найти в библиотеке", callback_data="lib:search")])
    rows.append([InlineKeyboardButton(text="🎲 Случайный трек", callback_data="lib:random")])
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def search_results_keyboard(tracks: list[Track]) -> InlineKeyboardMarkup:
    rows = _track_rows(tracks, first_number=1, back_page=1)
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="menu:library")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def track_card_keyboard(track_id: int, back_page: int) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="📂 Добавить в плейлист", callback_data="stub:playlists")],
        [InlineKeyboardButton(text="📤 Поделиться", callback_data="stub:share")],
        [InlineKeyboardButton(text="🗑 Удалить из библиотеки", callback_data=f"lib:del:{track_id}")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data=f"lib:page:{back_page}")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)

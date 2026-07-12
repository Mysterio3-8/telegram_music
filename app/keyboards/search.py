from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.config import settings
from app.db.models import Instrumental, Track


def _nav_row(page: int, total_pages: int, prefix: str) -> list[InlineKeyboardButton]:
    nav: list[InlineKeyboardButton] = []
    if page > 1:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"{prefix}:page:{page - 1}"))
    nav.append(InlineKeyboardButton(text=f"Страница {page} / {total_pages}", callback_data="noop"))
    if page < total_pages:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"{prefix}:page:{page + 1}"))
    return nav


def track_results_keyboard(
    tracks: list[Track], page: int, total_pages: int
) -> InlineKeyboardMarkup:
    first_number = (page - 1) * settings.page_size + 1
    rows = [
        [
            InlineKeyboardButton(
                text=f"{number}. {track.artist} — {track.title}",
                callback_data=f"trk:{track.id}:srch",
            )
        ]
        for number, track in enumerate(tracks, start=first_number)
    ]
    rows.append(_nav_row(page, total_pages, prefix="st"))
    if tracks:
        rows.append([InlineKeyboardButton(text="▶️ Слушать всё", callback_data="q:srch:0")])
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def instrumental_results_keyboard(
    instrumentals: list[Instrumental], page: int, total_pages: int
) -> InlineKeyboardMarkup:
    first_number = (page - 1) * settings.page_size + 1
    rows = [
        [
            InlineKeyboardButton(
                text=f"{number}. {item.artist} — {item.title}",
                callback_data=f"ins:open:{item.id}",
            )
        ]
        for number, item in enumerate(instrumentals, start=first_number)
    ]
    rows.append(_nav_row(page, total_pages, prefix="si"))
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def instrumental_card_keyboard(instrumental_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="▶️ Слушать", callback_data=f"ins:play:{instrumental_id}")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="si:back")],
        ]
    )

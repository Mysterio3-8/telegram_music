from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.config import settings
from app.db.models import Track
from app.i18n import t


def _track_rows(
    tracks: list[Track], first_number: int, back_page: int
) -> list[list[InlineKeyboardButton]]:
    return [
        [
            InlineKeyboardButton(
                text=f"{number}. {track.artist} — {track.title}",
                callback_data=f"trk:{track.id}:lib.{back_page}",
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
    nav.append(InlineKeyboardButton(text=t("common.page", page=page, total_pages=total_pages), callback_data="noop"))
    if page < total_pages:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"lib:page:{page + 1}"))
    rows.append(nav)

    rows.append([InlineKeyboardButton(text=t("library.search_button"), callback_data="lib:search")])
    if tracks:
        rows.append([InlineKeyboardButton(text=t("common.listen_all"), callback_data="q:lib:0")])
    rows.append([InlineKeyboardButton(text=t("common.mix"), callback_data="q:mix")])
    rows.append([InlineKeyboardButton(text=t("common.back"), callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def search_results_keyboard(tracks: list[Track]) -> InlineKeyboardMarkup:
    rows = _track_rows(tracks, first_number=1, back_page=1)
    rows.append([InlineKeyboardButton(text=t("common.back"), callback_data="menu:library")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

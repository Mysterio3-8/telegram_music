from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.config import settings
from app.db.models import Playlist, Track
from app.i18n import t


def playlists_keyboard(
    playlists: list[Playlist], page: int, total_pages: int
) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=playlist.title, callback_data=f"pl:open:{playlist.id}:1")]
        for playlist in playlists
    ]

    nav: list[InlineKeyboardButton] = []
    if page > 1:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"pls:page:{page - 1}"))
    nav.append(InlineKeyboardButton(text=t("common.page", page=page, total_pages=total_pages), callback_data="noop"))
    if page < total_pages:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"pls:page:{page + 1}"))
    rows.append(nav)

    rows.append([InlineKeyboardButton(text=t("playlists.create_button"), callback_data="pls:new")])
    rows.append([InlineKeyboardButton(text=t("common.back"), callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def playlist_view_keyboard(
    tracks: list[Track], playlist_id: int, page: int, total_pages: int
) -> InlineKeyboardMarkup:
    first_number = (page - 1) * settings.page_size + 1
    rows = [
        [
            InlineKeyboardButton(
                text=f"{number}. {track.artist} — {track.title}",
                callback_data=f"trk:{track.id}:pl.{playlist_id}.{page}",
            )
        ]
        for number, track in enumerate(tracks, start=first_number)
    ]

    nav: list[InlineKeyboardButton] = []
    if page > 1:
        nav.append(
            InlineKeyboardButton(text="⬅️", callback_data=f"pl:page:{playlist_id}:{page - 1}")
        )
    nav.append(InlineKeyboardButton(text=t("common.page", page=page, total_pages=total_pages), callback_data="noop"))
    if page < total_pages:
        nav.append(
            InlineKeyboardButton(text="➡️", callback_data=f"pl:page:{playlist_id}:{page + 1}")
        )
    rows.append(nav)

    if tracks:
        rows.append(
            [InlineKeyboardButton(text=t("common.listen_all"), callback_data=f"q:pl:{playlist_id}:0")]
        )
    rows.append(
        [InlineKeyboardButton(text=t("playlists.delete_button"), callback_data=f"pl:delask:{playlist_id}")]
    )
    rows.append([InlineKeyboardButton(text=t("common.back"), callback_data="menu:playlists")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_delete_keyboard(playlist_id: int) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=t("playlists.delete_yes"), callback_data=f"pl:del:{playlist_id}")],
        [InlineKeyboardButton(text=t("common.cancel"), callback_data=f"pl:open:{playlist_id}:1")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)

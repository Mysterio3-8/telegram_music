from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.db.models import Playlist, Track


def track_card_keyboard(track: Track, ctx: str, in_library: bool) -> InlineKeyboardMarkup:
    """ctx — откуда открыта карточка: lib.{page} | pl.{playlist_id}.{page} | srch"""
    rows: list[list[InlineKeyboardButton]] = []

    if in_library:
        rows.append(
            [InlineKeyboardButton(text="🗑 Удалить из библиотеки", callback_data=f"ta:dellib:{track.id}:{ctx}")]
        )
    else:
        rows.append(
            [InlineKeyboardButton(text="➕ Добавить в библиотеку", callback_data=f"ta:addlib:{track.id}:{ctx}")]
        )

    rows.append(
        [InlineKeyboardButton(text="📂 Добавить в плейлист", callback_data=f"ta:plmenu:{track.id}:{ctx}")]
    )
    if ctx.startswith("pl."):
        rows.append(
            [InlineKeyboardButton(text="🗑 Удалить из плейлиста", callback_data=f"ta:delpl:{track.id}:{ctx}")]
        )
    if track.storage_path and track.storage_path.startswith("tg://"):
        rows.append(
            [InlineKeyboardButton(text="⬇️ Скачать", callback_data=f"ta:file:{track.id}:{ctx}")]
        )
    rows.append([InlineKeyboardButton(text="📤 Поделиться", callback_data=f"ta:share:{track.id}:{ctx}")])
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data=f"back:{ctx}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def pick_playlist_keyboard(
    playlists: list[Playlist], track_id: int, ctx: str
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=playlist.title,
                callback_data=f"ta:pick_{playlist.id}:{track_id}:{ctx}",
            )
        ]
        for playlist in playlists
    ]
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data=f"trk:{track_id}:{ctx}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

from urllib.parse import quote

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.db.models import Playlist, Track


def share_url(track: Track, bot_username: str) -> str:
    """Системное окно Telegram «поделиться» с deep-link на трек (SPEC: доработки, п.4)."""
    link = f"https://t.me/{bot_username}?start=track_{track.id}"
    text = f"🎧 {track.artist} — {track.title}"
    return f"https://t.me/share/url?url={quote(link, safe='')}&text={quote(text, safe='')}"


def track_card_keyboard(
    track: Track,
    ctx: str,
    in_library: bool,
    bot_username: str,
    is_admin: bool = False,
) -> InlineKeyboardMarkup:
    """ctx — откуда открыта карточка: lib.{page} | pl.{playlist_id}.{page} | srch.

    Карточка — отдельное сообщение с плеером; «Назад» (back:del) просто удаляет её,
    предыдущий экран остаётся выше в чате.
    """
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
    if track.tg_file_id or track.storage_path:
        rows.append(
            [InlineKeyboardButton(text="⬇️ Скачать", callback_data=f"ta:file:{track.id}:{ctx}")]
        )
    rows.append([InlineKeyboardButton(text="📤 Поделиться", url=share_url(track, bot_username))])
    if is_admin:
        rows.append(
            [InlineKeyboardButton(text="✏️ Редактировать (админ)", callback_data=f"ta:edit:{track.id}:{ctx}")]
        )
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back:del")])
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
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data=f"ta:card:{track_id}:{ctx}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

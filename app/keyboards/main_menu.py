from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="🔍 Поиск треков", callback_data="menu:search")],
        [InlineKeyboardButton(text="🎵 Библиотека", callback_data="menu:library")],
        [InlineKeyboardButton(text="📂 Плейлисты", callback_data="menu:playlists")],
        [InlineKeyboardButton(text="🎼 Поиск минусов", callback_data="menu:instrumentals")],
        [InlineKeyboardButton(text="⬆️ Загрузить трек", callback_data="menu:upload")],
        [InlineKeyboardButton(text="💎 Купить Premium", callback_data="menu:premium")],
        [InlineKeyboardButton(text="🌐 Mini App", callback_data="menu:miniapp")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)

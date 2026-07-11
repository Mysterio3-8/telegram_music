from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="🔍 Поиск треков", callback_data="menu:search")],
        [InlineKeyboardButton(text="🎵 Библиотека", callback_data="menu:library")],
        [InlineKeyboardButton(text="📂 Плейлисты", callback_data="menu:playlists")],
        [InlineKeyboardButton(text="🎼 Поиск минусов", callback_data="menu:instrumentals")],
        [InlineKeyboardButton(text="⬆️ Загрузить трек", callback_data="menu:upload")],
        [InlineKeyboardButton(text="💎 Купить Premium", callback_data="menu:premium")],
        # 🌐 Mini App скрыта до готовности (SPEC §15); menu:miniapp в stubs.py оставлен,
        # чтобы кнопка в старых сообщениях не была мёртвой
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)

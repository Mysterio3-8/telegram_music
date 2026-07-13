from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from app.config import settings


def main_menu_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="🔍 Поиск треков", callback_data="menu:search")],
        [InlineKeyboardButton(text="🎵 Библиотека", callback_data="menu:library")],
        [InlineKeyboardButton(text="📂 Плейлисты", callback_data="menu:playlists")],
        [InlineKeyboardButton(text="🎼 Поиск минусов", callback_data="menu:instrumentals")],
        [InlineKeyboardButton(text="⬆️ Загрузить трек", callback_data="menu:upload")],
        [InlineKeyboardButton(text="💎 Купить Premium", callback_data="menu:premium")],
    ]
    if settings.public_base_url:
        rows.insert(
            0,
            [
                InlineKeyboardButton(
                    text="🎧 Открыть плеер",
                    web_app=WebAppInfo(url=settings.public_base_url),
                )
            ],
        )
    # menu:miniapp в stubs.py оставлен, чтобы кнопка в старых сообщениях не была мёртвой
    return InlineKeyboardMarkup(inline_keyboard=rows)

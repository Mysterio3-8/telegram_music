from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def admin_panel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Обновить", callback_data="adm:stats")],
            [InlineKeyboardButton(text="◀️ В меню", callback_data="menu:main")],
        ]
    )

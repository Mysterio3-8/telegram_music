from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def queue_continue_keyboard(next_callback: str, label: str = "▶️ Дальше") -> InlineKeyboardMarkup:
    """Кнопки под последним аудио пачки: продолжить очередь или остановиться."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=label, callback_data=next_callback)],
            [InlineKeyboardButton(text="⏹ Остановить", callback_data="q:stop")],
        ]
    )


def queue_end_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="◀️ В меню", callback_data="menu:main")]]
    )

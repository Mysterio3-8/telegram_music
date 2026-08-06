from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.i18n import t


def queue_continue_keyboard(next_callback: str, label: str | None = None) -> InlineKeyboardMarkup:
    """Кнопки под последним аудио пачки: продолжить очередь или остановиться.

    label=None — «Дальше» на языке пользователя; микс передаёт свою подпись."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=label or t("player.next"), callback_data=next_callback)],
            [InlineKeyboardButton(text=t("player.stop"), callback_data="q:stop")],
        ]
    )


def queue_end_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=t("common.back_to_menu"), callback_data="menu:main")]]
    )

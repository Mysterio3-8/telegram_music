"""Разметка экрана настроек. Только кнопки, без логики."""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.i18n import DEFAULT_LANGUAGE, t
from app.services.original_audio import QUALITY_MP3, QUALITY_ORIGINAL


def quality_keyboard(current: str, lang: str = DEFAULT_LANGUAGE) -> InlineKeyboardMarkup:
    """Выбор формата выдачи; текущий отмечен галочкой.

    Замок у оригинала не рисуем: кнопка нажимается всеми, а не-Premium получает
    объяснение с предложением подписки. Серая неактивная кнопка в Telegram
    выглядит как поломка — человек жмёт и не понимает, почему ничего не выходит.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("settings.quality_mp3", lang)
                    + (" ✅" if current != QUALITY_ORIGINAL else ""),
                    callback_data=f"set:q:{QUALITY_MP3}",
                )
            ],
            [
                InlineKeyboardButton(
                    text=t("settings.quality_original", lang)
                    + (" ✅" if current == QUALITY_ORIGINAL else ""),
                    callback_data=f"set:q:{QUALITY_ORIGINAL}",
                )
            ],
            [InlineKeyboardButton(text=t("settings.back", lang), callback_data="menu:main")],
        ]
    )

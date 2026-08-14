"""Разметка экрана настроек. Только кнопки, без логики."""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.i18n import DEFAULT_LANGUAGE, t
from app.services.original_audio import QUALITY_BEST, QUALITY_MP3


def settings_keyboard(
    current: str, cover_as_file: bool, lang: str = DEFAULT_LANGUAGE
) -> InlineKeyboardMarkup:
    """Весь экран настроек: качество плюс переключатель обложки."""
    rows = list(quality_keyboard(current, lang).inline_keyboard)
    back = rows.pop()  # «Назад» остаётся последней кнопкой
    rows.append(
        [
            InlineKeyboardButton(
                text=t("settings.cover_on" if cover_as_file else "settings.cover_off", lang),
                callback_data="set:cover",
            )
        ]
    )
    rows.append(back)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def quality_keyboard(current: str, lang: str = DEFAULT_LANGUAGE) -> InlineKeyboardMarkup:
    """Выбор качества выдачи; текущее отмечено галочкой.

    Замок не рисуем: кнопка нажимается всеми, а не-Premium получает
    объяснение с предложением подписки. Серая неактивная кнопка в Telegram
    выглядит как поломка — человек жмёт и не понимает, почему ничего не выходит.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("settings.quality_mp3", lang)
                    + (" ✅" if current != QUALITY_BEST else ""),
                    callback_data=f"set:q:{QUALITY_MP3}",
                )
            ],
            [
                InlineKeyboardButton(
                    text=t("settings.quality_best", lang)
                    + (" ✅" if current == QUALITY_BEST else ""),
                    callback_data=f"set:q:{QUALITY_BEST}",
                )
            ],
            [InlineKeyboardButton(text=t("settings.back", lang), callback_data="menu:main")],
        ]
    )

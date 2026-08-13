from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from app.config import settings
from app.i18n import DEFAULT_LANGUAGE, t


def main_menu_keyboard(lang: str = DEFAULT_LANGUAGE) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=t("menu.upload", lang), callback_data="menu:upload")],
        # Перенос плейлистов живёт в Mini App (решение владельца): в боте кнопка
        # лишняя. Команда /transfer и обработчик menu:transfer оставлены рабочими.
        [
            InlineKeyboardButton(
                text=t("menu.premium", lang, price=settings.premium_price_rub),
                callback_data="menu:premium",
            )
        ],
        [InlineKeyboardButton(text=t("menu.referral", lang), callback_data="menu:referral")],
        [InlineKeyboardButton(text=t("menu.settings", lang), callback_data="menu:settings")],
        [InlineKeyboardButton(text=t("menu.language", lang), callback_data="menu:lang")],
        # Кнопка поддержки («жалобы / идеи») временно убрана по решению владельца.
        # Сам бот @suptgmusic_bot жив — вернуть строку, когда понадобится:
        # [InlineKeyboardButton(text=t("menu.support", lang),
        #                       url=f"https://t.me/{settings.support_bot_username}")],
    ]
    if settings.public_base_url:
        rows.insert(
            0,
            [
                InlineKeyboardButton(
                    text=t("menu.player", lang),
                    web_app=WebAppInfo(url=settings.public_base_url),
                )
            ],
        )
    # menu:miniapp в stubs.py оставлен, чтобы кнопка в старых сообщениях не была мёртвой
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _language_buttons(current: str, prefix: str) -> list[list[InlineKeyboardButton]]:
    from app.i18n import LANGUAGES

    buttons = [
        InlineKeyboardButton(
            text=f"{item.flag} {item.title}" + (" ✅" if item.code == current else ""),
            callback_data=f"{prefix}{item.code}",
        )
        for item in LANGUAGES
    ]
    return [buttons[i : i + 2] for i in range(0, len(buttons), 2)]


def language_keyboard(current: str) -> InlineKeyboardMarkup:
    """Выбор языка по два в ряд; текущий отмечен галочкой."""
    rows = _language_buttons(current, "lang:set:")
    rows.append([InlineKeyboardButton(text=t("lang.back", current), callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def language_setup_keyboard(current: str) -> InlineKeyboardMarkup:
    """Первый экран новичка: тот же выбор, но без «Назад» — уходить некуда, а
    после выбора сразу открывается гейт подписки или кабинет (префикс lang:setup:)."""
    return InlineKeyboardMarkup(inline_keyboard=_language_buttons(current, "lang:setup:"))

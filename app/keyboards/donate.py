"""Разметка экранов доната. Только кнопки, без логики."""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.config import settings
from app.i18n import DEFAULT_LANGUAGE, t
from app.services.donations import DONATE_PRESETS


def donate_keyboard(lang: str = DEFAULT_LANGUAGE) -> InlineKeyboardMarkup:
    """Суммы по две в ряд, затем своя сумма, рейтинг, правила и назад."""
    amounts = [
        InlineKeyboardButton(text=f"{amount} ₽", callback_data=f"don:pay:{amount}")
        for amount in DONATE_PRESETS
    ]
    rows: list[list[InlineKeyboardButton]] = [
        amounts[i : i + 2] for i in range(0, len(amounts), 2)
    ]
    rows.append(
        [InlineKeyboardButton(text=t("donate.custom", lang), callback_data="don:custom")]
    )
    rows.append([InlineKeyboardButton(text=t("donate.top", lang), callback_data="don:top")])
    # Полные правила живут вне бота (решение владельца). Пока ссылка не задана —
    # кнопки нет: мёртвая кнопка хуже отсутствующей. Короткая версия правил всё
    # равно всегда на экране.
    if settings.donate_rules_url:
        rows.append(
            [InlineKeyboardButton(text=t("donate.rules", lang), url=settings.donate_rules_url)]
        )
    rows.append([InlineKeyboardButton(text=t("donate.back", lang), callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def donate_pay_keyboard(url: str, lang: str = DEFAULT_LANGUAGE) -> InlineKeyboardMarkup:
    """Ссылка на кассу плюс возврат к выбору суммы."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t("donate.pay", lang), url=url)],
            [InlineKeyboardButton(text=t("donate.back", lang), callback_data="don:open")],
        ]
    )


def donate_top_keyboard(lang: str = DEFAULT_LANGUAGE) -> InlineKeyboardMarkup:
    """С рейтинга — назад к выбору суммы, а не в главное меню: человек пришёл
    поддержать, и терять его на экране со списком незачем."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t("donate.support_now", lang), callback_data="don:open")],
            [InlineKeyboardButton(text=t("donate.back", lang), callback_data="menu:main")],
        ]
    )


def donate_cancel_keyboard(lang: str = DEFAULT_LANGUAGE) -> InlineKeyboardMarkup:
    """Отмена ввода своей суммы."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t("donate.back", lang), callback_data="don:open")]
        ]
    )

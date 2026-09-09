"""Разметка экранов доната. Только кнопки, без логики."""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.config import settings
from app.i18n import DEFAULT_LANGUAGE, t
from app.services.donations import DONATE_PRESETS


def donate_keyboard(
    lang: str = DEFAULT_LANGUAGE, *, anonymous: bool = False, has_goal: bool = False
) -> InlineKeyboardMarkup:
    """Суммы по две в ряд, тумблер анонимности, рейтинг, правила и назад."""
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
    # Тумблер стоит ВЫШЕ кнопок оплаты по смыслу, но ниже по месту: выбор суммы —
    # главное действие экрана, и отодвигать его вниз ради настройки нельзя.
    anon_key = "donate.anon_on" if anonymous else "donate.anon_off"
    rows.append([InlineKeyboardButton(text=t(anon_key, lang), callback_data="don:anon")])
    # Кнопка вклада в цель появляется только когда сбор идёт — иначе она вела бы
    # на пустой экран.
    if has_goal:
        rows.append(
            [InlineKeyboardButton(text=t("goal.switch_goal", lang), callback_data="don:goaltop")]
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


def donate_top_keyboard(
    lang: str = DEFAULT_LANGUAGE, *, showing_goal: bool = False, has_goal: bool = False
) -> InlineKeyboardMarkup:
    """С рейтинга — назад к выбору суммы, а не в главное меню: человек пришёл
    поддержать, и терять его на экране со списком незачем.

    Плюс переключатель между двумя рейтингами. Кнопка всегда называет ТО, КУДА
    ведёт, а не то, что открыто сейчас: подпись «за всё время» на экране «за всё
    время» читалась бы как заголовок, и по ней бы не нажимали.
    """
    rows: list[list[InlineKeyboardButton]] = []
    if showing_goal:
        rows.append(
            [InlineKeyboardButton(text=t("goal.switch_all", lang), callback_data="don:top")]
        )
    elif has_goal:
        rows.append(
            [InlineKeyboardButton(text=t("goal.switch_goal", lang), callback_data="don:goaltop")]
        )
    rows.append(
        [InlineKeyboardButton(text=t("donate.support_now", lang), callback_data="don:open")]
    )
    rows.append([InlineKeyboardButton(text=t("donate.back", lang), callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def donate_cancel_keyboard(lang: str = DEFAULT_LANGUAGE) -> InlineKeyboardMarkup:
    """Отмена ввода своей суммы."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t("donate.back", lang), callback_data="don:open")]
        ]
    )


def donate_method_keyboard(
    amount: int, ton_amount: float, lang: str = DEFAULT_LANGUAGE
) -> InlineKeyboardMarkup:
    """Выбор способа: рубли или TON.

    Показывается ТОЛЬКО когда TON действительно доступен. Иначе экран с одной
    кнопкой был бы лишним шагом между человеком и оплатой.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("donate.pay_rub", lang), callback_data=f"don:rub:{amount}"
                )
            ],
            [
                InlineKeyboardButton(
                    text=t("donate.pay_ton", lang).format(ton=ton_amount),
                    callback_data=f"don:ton:{amount}",
                )
            ],
            [InlineKeyboardButton(text=t("donate.back", lang), callback_data="don:open")],
        ]
    )

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.config import settings
from app.i18n import t


def premium_keyboard(card_available: bool, yookassa_available: bool = False) -> InlineKeyboardMarkup:
    """Тарифы 1/3/6/12 месяцев. Тап по тарифу ведёт на выбор способа оплаты.

    Способы не разложены прямо здесь сознательно: их два (Stars и рубли), и
    восемь кнопок вместо четырёх превратили бы экран в стену, где цена и валюта
    сливаются. Лишний тап дешевле, чем выбор вслепую.

    ⚠️ Аргументы `card_available`/`yookassa_available` сохранены: экран Premium
    зовёт клавиатуру с ними, и без хотя бы одного рублёвого способа Stars
    остаются единственным — это рабочее состояние, а не ошибка.
    """
    from app.services.premium import PREMIUM_PLAN_MONTHS, plan_discount_pct, plan_price_rub

    rows: list[list[InlineKeyboardButton]] = []
    for months in PREMIUM_PLAN_MONTHS:
        price = plan_price_rub(months)
        label = "месяц" if months == 1 else f"{months} мес"
        per_month = price // months
        # Выгоду показываем на самой кнопке: без цены месяца и размера скидки
        # длинный тариф выглядит просто как «дороже»
        suffix = "" if months == 1 else f" · {per_month} ₽/мес"
        discount = plan_discount_pct(months)
        if discount:
            suffix += f" · −{discount}%"
        rows.append(
            [
                InlineKeyboardButton(
                    text=t("premium.plan_button", label=label, price=price, suffix=suffix),
                    callback_data=f"prem:plan:{months}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text=t("common.back"), callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def payment_method_keyboard(
    months: int, card_available: bool, yookassa_available: bool
) -> InlineKeyboardMarkup:
    """Чем платить за выбранный тариф.

    Stars идут первыми (решение владельца): официальная партнёрская программа
    Telegram работает только с ними, со сторонним эквайрингом её не включить.
    ЮKassa остаётся рядом — у части аудитории звёзд нет, и терять этих людей
    нельзя.
    """
    from app.services.premium import plan_price_rub, plan_price_stars

    rows = [
        [
            InlineKeyboardButton(
                text=t("premium.pay_stars", stars=plan_price_stars(months)),
                callback_data=f"prem:stars:{months}",
            )
        ]
    ]
    if yookassa_available or card_available:
        target = "prem:yookassa" if yookassa_available else "prem:card"
        rows.append(
            [
                InlineKeyboardButton(
                    text=t("premium.pay_rub", price=plan_price_rub(months)),
                    callback_data=f"{target}:{months}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text=t("common.back"), callback_data="menu:premium")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def ad_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t("premium.disable_ads"), callback_data="menu:premium")],
            [InlineKeyboardButton(text=t("premium.continue"), callback_data="noop")],
        ]
    )

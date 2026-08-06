from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.config import settings
from app.i18n import t


def premium_keyboard(card_available: bool, yookassa_available: bool = False) -> InlineKeyboardMarkup:
    """Тарифы 1/3/6/12 месяцев, оплата только деньгами (Stars скрыты по решению
    владельца — оставлены в коде для приёма платежей, но из интерфейса убраны)."""
    from app.services.premium import PREMIUM_PLAN_MONTHS, plan_discount_pct, plan_price_rub

    rows: list[list[InlineKeyboardButton]] = []
    if yookassa_available or card_available:
        target = "prem:yookassa" if yookassa_available else "prem:card"
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
                        callback_data=f"{target}:{months}",
                    )
                ]
            )
    rows.append([InlineKeyboardButton(text=t("common.back"), callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def ad_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t("premium.disable_ads"), callback_data="menu:premium")],
            [InlineKeyboardButton(text=t("premium.continue"), callback_data="noop")],
        ]
    )

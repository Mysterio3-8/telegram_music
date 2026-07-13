from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.config import settings


def premium_keyboard(card_available: bool, yookassa_available: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"⭐ Оплатить Stars ({settings.premium_price_stars})",
                callback_data="prem:stars",
            )
        ]
    ]
    if yookassa_available:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"💳 Карта / СБП — {settings.premium_price_rub} ₽",
                    callback_data="prem:yookassa",
                )
            ]
        )
    elif card_available:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"💳 Картой / СБП ({settings.premium_price_rub} ₽)",
                    callback_data="prem:card",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def ad_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💎 Отключить рекламу (Premium)", callback_data="menu:premium")],
            [InlineKeyboardButton(text="Продолжить использование", callback_data="noop")],
        ]
    )

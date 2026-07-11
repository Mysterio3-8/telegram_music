import logging
from datetime import datetime

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
)

from app.config import settings
from app.db.base import session_factory
from app.handlers.common import ensure_user
from app.keyboards.premium import premium_keyboard
from app.services.premium import activate_premium, is_premium_active

router = Router()
logger = logging.getLogger(__name__)

PAYLOAD_STARS = "premium_stars"
PAYLOAD_CARD = "premium_card"

_BENEFITS = (
    "• Отключение рекламы\n"
    "• Неограниченные плейлисты\n"
    "• Увеличенный лимит загрузок\n"
    "• Ранний доступ к новым функциям\n"
    "• Поддержка проекта"
)


def _premium_text(active: bool, premium_until: datetime | None) -> str:
    if active and premium_until is not None:
        return (
            f"💎 Premium активен до {premium_until.strftime('%d.%m.%Y')}\n\n"
            f"{_BENEFITS}\n\n"
            f"Можно продлить ещё на {settings.premium_duration_days} дней:"
        )
    return (
        "💎 Premium\n\n"
        f"{_BENEFITS}\n\n"
        f"Цена: {settings.premium_price_rub} ₽ / {settings.premium_price_stars} ⭐ "
        f"на {settings.premium_duration_days} дней."
    )


@router.callback_query(F.data == "menu:premium")
async def cb_premium(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    async with session_factory() as session:
        user = await ensure_user(session, callback.from_user)
        active = is_premium_active(user)
        premium_until = user.premium_until
    await callback.message.edit_text(
        _premium_text(active, premium_until),
        reply_markup=premium_keyboard(card_available=bool(settings.payment_provider_token)),
    )
    await callback.answer()


@router.callback_query(F.data == "prem:stars")
async def cb_pay_stars(callback: CallbackQuery) -> None:
    await callback.message.answer_invoice(
        title=f"Premium на {settings.premium_duration_days} дней",
        description="Отключение рекламы, безлимит плейлистов, увеличенный лимит загрузок.",
        payload=PAYLOAD_STARS,
        currency="XTR",
        prices=[LabeledPrice(label="Premium", amount=settings.premium_price_stars)],
    )
    await callback.answer()


@router.callback_query(F.data == "prem:card")
async def cb_pay_card(callback: CallbackQuery) -> None:
    if not settings.payment_provider_token:
        await callback.answer("Оплата картой пока недоступна", show_alert=True)
        return
    await callback.message.answer_invoice(
        title=f"Premium на {settings.premium_duration_days} дней",
        description="Отключение рекламы, безлимит плейлистов, увеличенный лимит загрузок.",
        payload=PAYLOAD_CARD,
        provider_token=settings.payment_provider_token,
        currency="RUB",
        prices=[LabeledPrice(label="Premium", amount=settings.premium_price_rub * 100)],
    )
    await callback.answer()


@router.pre_checkout_query()
async def cb_pre_checkout(pre_checkout_query: PreCheckoutQuery) -> None:
    ok = pre_checkout_query.invoice_payload in (PAYLOAD_STARS, PAYLOAD_CARD)
    await pre_checkout_query.answer(ok=ok, error_message=None if ok else "Некорректный платёж")


@router.message(F.successful_payment)
async def cb_successful_payment(message: Message) -> None:
    payment = message.successful_payment
    payment_type = "stars" if payment.currency == "XTR" else "card"
    async with session_factory() as session:
        user = await ensure_user(session, message.from_user)
        updated = await activate_premium(
            session, user.id, payment_type, payment.telegram_payment_charge_id
        )
        until = updated.premium_until
    logger.info(
        "Premium activated user=%s type=%s charge=%s",
        message.from_user.id,
        payment_type,
        payment.telegram_payment_charge_id,
    )
    await message.answer(
        f"✅ Premium активирован до {until.strftime('%d.%m.%Y')}! Спасибо за поддержку 💛",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="◀️ В меню", callback_data="menu:main")]]
        ),
    )

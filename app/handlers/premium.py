import logging
from datetime import datetime

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
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
from app.services.revenue import record_payment
from app.services.yookassa_payments import create_premium_payment, is_yookassa_configured
from app.i18n import t

router = Router()
logger = logging.getLogger(__name__)

PAYLOAD_STARS = "premium_stars"
PAYLOAD_CARD = "premium_card"

_BENEFITS = (
    "🚫 <b>Без рекламы</b> — ни баннеров, ни пауз\n"
    "📥 <b>Офлайн-режим</b> — качайте треки, слушайте без интернета\n"
    "🔄 <b>Перенос пачкой</b> — целые плейлисты из Spotify, Яндекса, ВК, SoundCloud\n"
    "🎼 <b>Без лимитов</b> — сколько угодно плейлистов и своих загрузок\n"
    "🎛 <b>Эквалайзер и таймер сна</b> — 20 пресетов, засыпайте под музыку\n"
    "📝 <b>Тексты песен</b> — добавляйте и редактируйте\n"
    "🎁 <b>Дни в подарок</b> — достижения и друзья приносят ещё Premium"
)


def plan_label(months: int) -> str:
    """«месяц» / «3 месяца» / «год» — срок словами, для текста платежа."""
    if months == 12:
        return "год"
    if months == 1:
        return "месяц"
    return f"{months} месяца" if months < 5 else f"{months} месяцев"


def _premium_text(active: bool, premium_until: datetime | None) -> str:
    if active and premium_until is not None:
        return (
            f"💎 <b>Premium активен</b> до {premium_until.strftime('%d.%m.%Y')}\n\n"
            f"{_BENEFITS}\n\n"
            f"Можно продлить заранее — дни суммируются."
        )
    return (
        "💎 <b>TG Music Premium</b>\n\n"
        f"{_BENEFITS}\n\n"
        f"Всего <b>{settings.premium_price_rub} ₽ в месяц</b> — дешевле чашки кофе. "
        "Чем длиннее тариф, тем ниже цена месяца.\n\n"
        "Выберите срок:"
    )


@router.callback_query(F.data == "menu:premium")
async def cb_premium(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(None)  # данные поиска сохраняем — экраны выше остаются рабочими
    async with session_factory() as session:
        user = await ensure_user(session, callback.from_user)
        active = is_premium_active(user)
        premium_until = user.premium_until
    await callback.message.edit_text(
        _premium_text(active, premium_until),
        parse_mode="HTML",
        reply_markup=premium_keyboard(
            card_available=bool(settings.payment_provider_token),
            yookassa_available=is_yookassa_configured(),
        ),
    )
    await callback.answer()


@router.callback_query(F.data == "prem:stars")
async def cb_pay_stars(callback: CallbackQuery) -> None:
    try:
        await callback.message.answer_invoice(
            title=f"Premium на {settings.premium_duration_days} дней",
            description=t("premium.invoice_description"),
            payload=PAYLOAD_STARS,
            currency="XTR",
            prices=[LabeledPrice(label="Premium", amount=settings.premium_price_stars)],
        )
    except TelegramBadRequest:
        logger.exception("Не удалось выставить счёт Stars user=%s", callback.from_user.id)
        await callback.answer(t("premium.invoice_failed"), show_alert=True)
        return
    await callback.answer()


@router.callback_query(F.data.startswith("prem:yookassa"))
async def cb_pay_yookassa(callback: CallbackQuery) -> None:
    """Оплата через API ЮKassa: платёж создаётся напрямую, пользователь получает
    ссылку на страницу оплаты. Подтверждение придёт webhook-ом на API-сервис.
    Хвост callback_data — срок тарифа в месяцах (1/3/6/12)."""
    from app.services.premium import plan_price_rub, plan_valid

    parts = callback.data.split(":")

    months = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 1
    if not plan_valid(months):
        months = 1
    price = plan_price_rub(months)
    url = await create_premium_payment(
        callback.from_user.id, settings.bot_username, price_rub=price, months=months
    )
    if url is None:
        await callback.answer(t("premium.payment_failed"), show_alert=True)
        return
    # Сумма и срок — из ВЫБРАННОГО тарифа. Раньше здесь стояли значения месячного
    # тарифа из настроек: за год списывалось 348 ₽, а в тексте стояло
    # «29 ₽ — Premium на 30 дней».
    await callback.message.answer(
        f"💳 Оплата {price} ₽ — Premium на {plan_label(months)}.\n\n"
        "Нажмите кнопку, оплатите любым удобным способом и вернитесь в бот — "
        "Premium включится автоматически в течение минуты.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=t("premium.pay_button", price=price), url=url)],
                [InlineKeyboardButton(text=t("common.back_to_menu"), callback_data="menu:main")],
            ]
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("prem:card"))
async def cb_pay_card(callback: CallbackQuery) -> None:
    """Оплата банковской картой / СБП через платёжного провайдера Telegram Payments.

    Провайдер подключается токеном PAYMENT_PROVIDER_TOKEN из BotFather (ЮKassa,
    Сбербанк и др.) — без изменения кода. Payload различает тарифы, что оставляет
    задел под новые виды подписок.
    """
    from app.services.premium import plan_price_rub, plan_valid

    if not settings.payment_provider_token:
        await callback.answer(t("premium.card_unavailable"), show_alert=True)
        return
    parts = callback.data.split(":")
    months = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 1
    if not plan_valid(months):
        months = 1
    price = plan_price_rub(months)
    try:
        await callback.message.answer_invoice(
            title=f"Premium на {plan_label(months)}",
            description=t("premium.invoice_description"),
            # Срок едет в payload: без него оплата года включала месяц —
            # успешный платёж не знал, за какой тариф заплатили
            payload=f"{PAYLOAD_CARD}:{months}",
            provider_token=settings.payment_provider_token,
            currency="RUB",
            prices=[LabeledPrice(label="Premium", amount=price * 100)],
        )
    except TelegramBadRequest:
        # Типовые причины: неверный/тестовый токен провайдера, сумма ниже минимальной
        logger.exception("Не удалось выставить счёт (карта) user=%s", callback.from_user.id)
        await callback.answer(
            t("premium.invoice_failed_card"), show_alert=True
        )
        return
    await callback.answer()


@router.pre_checkout_query()
async def cb_pre_checkout(pre_checkout_query: PreCheckoutQuery) -> None:
    payload = pre_checkout_query.invoice_payload or ""
    ok = payload == PAYLOAD_STARS or payload.split(":")[0] == PAYLOAD_CARD
    if not ok:
        logger.warning(
            "Отклонён pre_checkout user=%s payload=%r",
            pre_checkout_query.from_user.id,
            pre_checkout_query.invoice_payload,
        )
    await pre_checkout_query.answer(
        ok=ok, error_message=None if ok else t("premium.bad_payment")
    )


@router.message(F.successful_payment)
async def cb_successful_payment(message: Message) -> None:
    payment = message.successful_payment
    payment_type = "stars" if payment.currency == "XTR" else "card"
    # Срок оплаченного тарифа лежит в payload («premium_card:12»); без него
    # оплата года включала бы месяц
    payload_parts = (payment.invoice_payload or "").split(":")
    months = int(payload_parts[1]) if len(payload_parts) > 1 and payload_parts[1].isdigit() else 1
    async with session_factory() as session:
        user = await ensure_user(session, message.from_user)
        updated = await activate_premium(
            session, user.id, payment_type, payment.telegram_payment_charge_id, months=months
        )
        until = updated.premium_until
        # Лог выручки (блок E): карта в рублях (total_amount в копейках), Stars — 0 ₽
        amount_rub = payment.total_amount // 100 if payment.currency != "XTR" else 0
        await record_payment(
            session, user.id, amount_rub, payment_type, payment.telegram_payment_charge_id
        )
    logger.info(
        "Premium activated user=%s type=%s charge=%s",
        message.from_user.id,
        payment_type,
        payment.telegram_payment_charge_id,
    )
    await message.answer(
        f"✅ Premium активирован до {until.strftime('%d.%m.%Y')}! Спасибо за поддержку 💛",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text=t("common.back_to_menu"), callback_data="menu:main")]]
        ),
    )

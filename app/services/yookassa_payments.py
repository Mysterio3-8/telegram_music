"""Оплата Premium через API ЮKassa (redirect-сценарий, доп. запрос пользователя).

Отличие от Telegram Payments (prem:card): платёж создаётся напрямую в ЮKassa,
пользователь уходит на страницу оплаты и платит любым способом (карта, СБП,
SberPay…), подтверждение приходит webhook-ом на /webhook/yookassa.

Webhook НЕ доверяет телу уведомления: статус перепроверяется запросом к API
ЮKassa по payment_id (рекомендация ЮKassa против подделки уведомлений).
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone

import aiohttp
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import PremiumSubscription, User
from app.services.premium import activate_premium

logger = logging.getLogger(__name__)

YOOKASSA_API = "https://api.yookassa.ru/v3"


def is_yookassa_configured() -> bool:
    return bool(settings.yookassa_shop_id and settings.yookassa_secret_key)


def _auth() -> aiohttp.BasicAuth:
    return aiohttp.BasicAuth(settings.yookassa_shop_id, settings.yookassa_secret_key)


async def create_premium_payment(
    telegram_id: int, bot_username: str, price_rub: int | None = None, months: int = 1
) -> str | None:
    """Создаёт платёж, возвращает confirmation_url или None при ошибке."""
    amount = settings.premium_price_rub if price_rub is None else price_rub
    payload = {
        "amount": {"value": f"{amount}.00", "currency": "RUB"},
        "capture": True,
        "confirmation": {
            "type": "redirect",
            "return_url": f"https://t.me/{bot_username}",
        },
        "description": f"Premium на {settings.premium_duration_days * months} дней",
        "metadata": {"telegram_id": str(telegram_id), "months": str(months)},
        # Сохраняем способ оплаты для автопродления (блок E): согласие пользователь
        # даёт офертой при оформлении. Только для месячного тарифа.
        "save_payment_method": bool(settings.premium_autorenew and months == 1),
    }
    try:
        async with aiohttp.ClientSession(auth=_auth()) as http:
            async with http.post(
                f"{YOOKASSA_API}/payments",
                json=payload,
                headers={"Idempotence-Key": str(uuid.uuid4())},
            ) as response:
                body = await response.json()
                if response.status != 200:
                    logger.error("ЮKassa create payment %s: %s", response.status, body)
                    return None
                return body["confirmation"]["confirmation_url"]
    except aiohttp.ClientError:
        logger.exception("ЮKassa недоступна (create payment)")
        return None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def _charge_saved_method(session: AsyncSession, user: User) -> bool:
    """Рекуррентное списание 49 ₽ с сохранённого способа. True — Premium продлён.
    Идемпотентно по эффекту: после успеха premium_until уходит за окно и следующий
    прогон таймера юзера не трогает."""
    amount = settings.premium_price_rub
    payload = {
        "amount": {"value": f"{amount}.00", "currency": "RUB"},
        "capture": True,
        "payment_method_id": user.pay_method_id,
        "description": f"Автопродление Premium на {settings.premium_duration_days} дней",
        "metadata": {"telegram_id": str(user.telegram_id), "months": "1"},
    }
    try:
        async with aiohttp.ClientSession(auth=_auth()) as http:
            async with http.post(
                f"{YOOKASSA_API}/payments",
                json=payload,
                headers={"Idempotence-Key": str(uuid.uuid4())},
            ) as response:
                body = await response.json()
    except aiohttp.ClientError:
        logger.exception("ЮKassa недоступна (автопродление user=%s)", user.id)
        return False
    if body.get("status") != "succeeded":
        logger.warning("Автопродление user=%s не succeeded: %s", user.id, body.get("status"))
        return False

    await activate_premium(session, user.id, "yookassa", body["id"], months=1)
    from app.services.revenue import record_payment

    await record_payment(session, user.id, amount, "yookassa", body["id"])
    logger.info("Автопродление user=%s на %s ₽ (payment=%s)", user.id, amount, body["id"])
    return True


async def charge_due_subscriptions(session: AsyncSession) -> int:
    """Продлевает подписки, истекающие в ближайшие сутки, у кого включено
    автопродление и сохранён способ оплаты. Возвращает число продлений."""
    if not (settings.premium_autorenew and is_yookassa_configured()):
        return 0
    now = _utcnow()
    window = now + timedelta(days=1)
    users = list(
        (
            await session.scalars(
                select(User).where(
                    User.autorenew.is_(True),
                    User.pay_method_id.is_not(None),
                    User.premium.is_(True),
                    User.premium_until.is_not(None),
                    User.premium_until <= window,
                    User.premium_until > now,
                )
            )
        ).all()
    )
    charged = 0
    for user in users:
        if await _charge_saved_method(session, user):
            charged += 1
    return charged


async def fetch_payment(payment_id: str) -> dict | None:
    """Актуальное состояние платежа из API ЮKassa — источник истины для webhook."""
    try:
        async with aiohttp.ClientSession(auth=_auth()) as http:
            async with http.get(f"{YOOKASSA_API}/payments/{payment_id}") as response:
                if response.status != 200:
                    logger.error("ЮKassa fetch payment %s: HTTP %s", payment_id, response.status)
                    return None
                return await response.json()
    except aiohttp.ClientError:
        logger.exception("ЮKassa недоступна (fetch payment %s)", payment_id)
        return None


async def apply_succeeded_payment(session: AsyncSession, payment: dict) -> bool:
    """Активирует Premium по подтверждённому платежу. Идемпотентен по payment_id."""
    if payment.get("status") != "succeeded":
        return False
    telegram_id_raw = (payment.get("metadata") or {}).get("telegram_id")
    if not telegram_id_raw or not str(telegram_id_raw).isdigit():
        logger.error("Платёж %s без telegram_id в metadata", payment.get("id"))
        return False

    from app.services.users import get_user_by_telegram_id

    user = await get_user_by_telegram_id(session, int(telegram_id_raw))
    if user is None:
        logger.error("Платёж %s: пользователь tg=%s не найден", payment.get("id"), telegram_id_raw)
        return False

    subscription = await session.get(PremiumSubscription, user.id)
    if subscription is not None and subscription.payment_id == payment["id"]:
        return True  # повторное уведомление — уже обработано

    months_raw = (payment.get("metadata") or {}).get("months", "1")
    months = int(months_raw) if str(months_raw).isdigit() else 1
    await activate_premium(session, user.id, "yookassa", payment["id"], months=months)
    # Автопродление (блок E): сохраняем способ оплаты для будущих списаний
    method = payment.get("payment_method") or {}
    if method.get("saved") and method.get("id"):
        user.pay_method_id = method["id"]
        user.autorenew = True
    # Лог выручки (блок E): сумма из подтверждённого платежа
    from app.services.revenue import record_payment

    amount_raw = ((payment.get("amount") or {}).get("value")) or "0"
    amount_rub = int(float(amount_raw))
    await record_payment(session, user.id, amount_rub, "yookassa", payment["id"])
    # Пригласивший получает скидку на следующий месяц (доп. ТЗ, реферальная программа)
    from app.services.gamification import grant_referrer_discount

    await grant_referrer_discount(session, user)
    logger.info("Premium activated via YooKassa user=%s payment=%s", user.id, payment["id"])
    return True

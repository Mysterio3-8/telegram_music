"""Webhook ЮKassa + создание платежа из Mini App."""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.config import settings
from app.db.models import User
from app.services.yookassa_payments import (
    apply_succeeded_payment,
    create_premium_payment,
    fetch_payment,
    is_yookassa_configured,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["payments"])


class PaymentLinkOut(BaseModel):
    confirmation_url: str


@router.post("/premium/pay", response_model=PaymentLinkOut)
async def create_payment_link(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> PaymentLinkOut:
    if not is_yookassa_configured():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Оплата временно недоступна")
    discount = user.premium_discount_pct or 0
    price = settings.premium_price_rub * (100 - discount) // 100 if discount else settings.premium_price_rub
    url = await create_premium_payment(user.telegram_id, settings.bot_username, price)
    if url is None:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Не удалось создать платёж")
    if discount:
        user.premium_discount_pct = 0
        await session.commit()
    return PaymentLinkOut(confirmation_url=url)


@router.post("/webhook/yookassa")
async def yookassa_webhook(request: Request, session: AsyncSession = Depends(get_db)) -> dict:
    """Уведомления ЮKassa. Телу не доверяем — статус перепроверяется у API по id.

    Всегда 200 при обработанном уведомлении: иначе ЮKassa ретраит и в итоге
    отключает webhook.
    """
    try:
        body = await request.json()
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Не JSON")

    payment_id = ((body or {}).get("object") or {}).get("id")
    event = (body or {}).get("event", "")
    if not payment_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Нет object.id")

    if event != "payment.succeeded":
        return {"ok": True}  # canceled / waiting_for_capture — просто подтверждаем приём

    payment = await fetch_payment(payment_id)
    if payment is None:
        # ЮKassa недоступна — пусть ретраит уведомление позже
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Не удалось проверить платёж")

    await apply_succeeded_payment(session, payment)
    return {"ok": True}

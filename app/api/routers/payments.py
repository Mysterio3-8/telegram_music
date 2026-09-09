"""Webhook ЮKassa + создание платежа из Mini App."""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.config import settings
from app.db.models import User
from app.services.premium import plan_price_rub, plan_valid
from app.services.yookassa_payments import (
    apply_refund,
    apply_succeeded_payment,
    create_premium_payment,
    fetch_payment,
    is_yookassa_configured,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["payments"])


class PaymentLinkOut(BaseModel):
    confirmation_url: str


class PaymentIn(BaseModel):
    months: int = 1


@router.post("/premium/pay", response_model=PaymentLinkOut)
async def create_payment_link(
    payload: PaymentIn | None = None,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> PaymentLinkOut:
    if not is_yookassa_configured():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Оплата временно недоступна")
    months = payload.months if payload else 1
    if not plan_valid(months):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Неизвестный тариф")
    discount = user.premium_discount_pct or 0
    price = plan_price_rub(months, discount)
    url = await create_premium_payment(user.telegram_id, settings.bot_username, price, months=months)
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

    if event == "refund.succeeded":
        # Возврат приходит СВОИМ объектом: object.id — это id возврата, а нужный
        # нам платёж лежит в object.payment_id. Перепутать их значит не найти
        # донат и молча оставить человека в топе за уже возвращённые деньги.
        refunded_payment_id = ((body or {}).get("object") or {}).get("payment_id")
        if not refunded_payment_id:
            return {"ok": True}
        # Телу уведомления не доверяем — как и для payment.succeeded. Иначе
        # подделанный refund снимал бы кого угодно с рейтинга: id платежей
        # видны в личке донатера и в чеке.
        payment = await fetch_payment(str(refunded_payment_id))
        if payment is None:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Не удалось проверить возврат")
        refunded = float(((payment.get("refunded_amount") or {}).get("value")) or 0)
        if refunded > 0:
            await apply_refund(session, str(refunded_payment_id))
        else:
            logger.warning(
                "refund.succeeded по %s, но API ЮKassa не показывает возврата — игнорирую",
                refunded_payment_id,
            )
        return {"ok": True}

    if event != "payment.succeeded":
        return {"ok": True}  # canceled / waiting_for_capture — просто подтверждаем приём

    payment = await fetch_payment(payment_id)
    if payment is None:
        # ЮKassa недоступна — пусть ретраит уведомление позже
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Не удалось проверить платёж")

    await apply_succeeded_payment(session, payment)
    return {"ok": True}


@router.post("/webhook/walletpay")
async def walletpay_webhook(request: Request, session: AsyncSession = Depends(get_db)) -> dict:
    """Уведомления Wallet Pay об оплаченных заказах (донаты в TON).

    Два рубежа, и оба обязательны:
    1. **подпись** — иначе кто угодно, зная адрес вебхука, дарил бы себе места в
       рейтинге спонсоров одним curl-ом;
    2. **перепроверка у API** — как и у ЮKassa, телу уведомления не доверяем:
       подпись подтверждает отправителя, но не то, что заказ действительно
       оплачен. Если API недоступен, отвечаем 502 — Wallet Pay повторит.

    ⚠️ Формат уведомления не подтверждён живым запросом (см. docstring
    app/services/wallet_pay.py). Поэтому неудачная проверка подписи пишет в
    журнал обе подписи и отвечает 403: платёж не теряется — уведомление
    повторится, а по записи в журнале формулу можно поправить.
    """
    from app.services import wallet_pay

    if not settings.wallet_pay_api_key:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "TON-оплата не настроена")

    raw = await request.body()
    timestamp = request.headers.get("Walletpay-Timestamp", "")
    signature = request.headers.get("Walletpay-Signature", "")
    if not wallet_pay.verify_signature(
        request.method, request.url.path, timestamp, raw, signature
    ):
        logger.error(
            "Wallet Pay: подпись не сошлась (путь %s, метка %s, пришло %r). "
            "Если платежи реальные — сверьте формулу в wallet_pay.verify_signature.",
            request.url.path,
            timestamp,
            signature,
        )
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Подпись не совпала")

    try:
        body = await request.json()
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Не JSON")

    order = wallet_pay.extract_order(body)
    order_id = order.get("id") or order.get("orderId") or order.get("externalId")
    if not order_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "В уведомлении нет id заказа")

    checked = await wallet_pay.get_order_status(str(order_id))
    if checked is None:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Не удалось проверить заказ")

    await wallet_pay.apply_paid_order(session, wallet_pay.extract_order(checked))
    return {"ok": True}

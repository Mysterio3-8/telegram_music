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


def _payment_payload(
    telegram_id: int, bot_username: str, amount: int, months: int, with_save_method: bool
) -> dict:
    payload = {
        "amount": {"value": f"{amount}.00", "currency": "RUB"},
        "capture": True,
        "confirmation": {
            "type": "redirect",
            "return_url": f"https://t.me/{bot_username}",
        },
        "description": f"Premium на {settings.premium_duration_days * months} дней",
        "metadata": {"telegram_id": str(telegram_id), "months": str(months)},
    }
    if with_save_method:
        # Сохраняем способ оплаты для автопродления (блок E): согласие пользователь
        # даёт офертой при оформлении. Только для месячного тарифа.
        payload["save_payment_method"] = True
    return payload


async def _post_payment(payload: dict) -> tuple[int, dict]:
    async with aiohttp.ClientSession(auth=_auth()) as http:
        async with http.post(
            f"{YOOKASSA_API}/payments",
            json=payload,
            headers={"Idempotence-Key": str(uuid.uuid4())},
        ) as response:
            return response.status, await response.json()


async def create_premium_payment(
    telegram_id: int, bot_username: str, price_rub: int | None = None, months: int = 1
) -> str | None:
    """Создаёт платёж, возвращает confirmation_url или None при ошибке."""
    amount = settings.premium_price_rub if price_rub is None else price_rub
    want_save_method = bool(settings.premium_autorenew and months == 1)
    payload = _payment_payload(telegram_id, bot_username, amount, months, want_save_method)
    try:
        status, body = await _post_payment(payload)
        if status != 200 and want_save_method and body.get("code") == "forbidden":
            # Магазин не подключил рекуррентные платежи в ЮKassa — платежи не должны
            # падать из-за этого, повторяем без сохранения способа оплаты
            logger.warning("ЮKassa: рекуррент недоступен для магазина, повтор без save_payment_method")
            payload = _payment_payload(telegram_id, bot_username, amount, months, False)
            status, body = await _post_payment(payload)
        if status != 200:
            logger.error("ЮKassa create payment %s: %s", status, body)
            return None
        return body["confirmation"]["confirmation_url"]
    except aiohttp.ClientError:
        logger.exception("ЮKassa недоступна (create payment)")
        return None


async def create_donation_payment(
    telegram_id: int, bot_username: str, amount_rub: int, *, anonymous: bool = False
) -> str | None:
    """Платёж-донат. Возвращает confirmation_url или None при ошибке.

    ⚠️ metadata.kind="donate" — по нему вебхук отличает донат от покупки
    Premium. Без метки подтверждённый донат ушёл бы в activate_premium, то есть
    человек получил бы за дарение услугу, а это уже реализация со всеми
    последствиями по 54-ФЗ.

    save_payment_method здесь не запрашивается ни при каких настройках: донат
    разовый, списывать с человека потом нечего.
    """
    from app.services.donations import is_allowed_amount

    # Вторая проверка суммы, у самой границы с деньгами. Первая стоит в хендлере,
    # но между ними FSM и callback_data, а цена ошибки здесь — реальный платёж.
    if not is_allowed_amount(amount_rub):
        logger.error("Донат: сумма %s вне допустимых границ", amount_rub)
        return None
    payload = {
        "amount": {"value": f"{amount_rub}.00", "currency": "RUB"},
        "capture": True,
        "confirmation": {"type": "redirect", "return_url": f"https://t.me/{bot_username}"},
        "description": f"Добровольная поддержка проекта — {amount_rub} \u20bd",
        # ⚠️ Выбор «анонимно» едет в метаданных платежа, а не в FSM бота: между
        # нажатием и подтверждением человек уходит на сайт кассы, возвращается
        # когда угодно и не обязательно в бот, а уведомление и вовсе приходит в
        # другой процесс. Метаданные — единственное, что переживёт весь путь.
        "metadata": {
            "telegram_id": str(telegram_id),
            "kind": "donate",
            "anonymous": "1" if anonymous else "0",
        },
    }
    try:
        status, body = await _post_payment(payload)
        if status != 200:
            logger.error("ЮKassa create donation %s: %s", status, body)
            return None
        return body["confirmation"]["confirmation_url"]
    except aiohttp.ClientError:
        logger.exception("ЮKassa недоступна (create donation)")
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


def _amount_to_rub(amount_raw: str, payment_id: str | None) -> int:
    """Сумма ЮKassa ("78.00") → целые рубли.

    ⚠️ Округление, а не усечение. Все текущие тарифы и суммы донатов целые, но
    журнал денег обязан быть точным: усечение молча занижало бы выручку на
    копейку с каждой нецелой суммы, а заметить это можно только сверкой с
    кабинетом кассы. Нецелая сумма дополнительно пишется в журнал — значит,
    где-то появился тариф, под который журнал не рассчитан.
    """
    value = float(amount_raw)
    rub = round(value)
    if abs(value - rub) > 1e-9:
        logger.warning(
            "Платёж %s на нецелую сумму %s — в журнал уйдёт %s ₽. "
            "Если такие тарифы теперь норма, журнал надо переводить на копейки.",
            payment_id,
            amount_raw,
            rub,
        )
    return int(rub)


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

    # Донат обрабатывается отдельно и НИЧЕГО не выдаёт: это дарение, встречной
    # услуги у него нет по определению. Развилка стоит до всего остального,
    # чтобы ни одна ветка активации Premium не могла сработать по донату.
    if (payment.get("metadata") or {}).get("kind") == "donate":
        return await _apply_donation(session, user, payment)

    # Идемпотентность по ЖУРНАЛУ платежей, а не по текущему состоянию подписки.
    # ⚠️ Прежняя проверка сравнивала id с последним применённым платежом и
    # ломалась при втором платеже: заплатил месяц (A), заплатил год (B) —
    # состояние стало B, и повторное уведомление по A (ЮKassa повторяет часами)
    # выдавало лишний месяц и дубль в выручке.
    from app.services.revenue import payment_already_recorded, record_payment

    if await payment_already_recorded(session, payment["id"]):
        return True  # повторное уведомление — уже обработано
    # Второй рубеж для платежей, применённых до появления журнала: у них строки
    # в payments нет, и по одному журналу повтор был бы не виден.
    subscription = await session.get(PremiumSubscription, user.id)
    if subscription is not None and subscription.payment_id == payment["id"]:
        return True

    months_raw = (payment.get("metadata") or {}).get("months", "1")
    months = int(months_raw) if str(months_raw).isdigit() else 1
    await activate_premium(session, user.id, "yookassa", payment["id"], months=months)
    # Автопродление (блок E): сохраняем способ оплаты для будущих списаний
    method = payment.get("payment_method") or {}
    if method.get("saved") and method.get("id"):
        user.pay_method_id = method["id"]
        user.autorenew = True
    # Лог выручки (блок E): сумма из подтверждённого платежа
    amount_raw = ((payment.get("amount") or {}).get("value")) or "0"
    amount_rub = _amount_to_rub(amount_raw, payment.get("id"))
    await record_payment(session, user.id, amount_rub, "yookassa", payment["id"])
    # Пригласивший получает скидку на следующий месяц (доп. ТЗ, реферальная программа)
    from app.services.gamification import grant_referrer_discount

    await grant_referrer_discount(session, user)
    logger.info("Premium activated via YooKassa user=%s payment=%s", user.id, payment["id"])
    return True


async def _apply_donation(session: AsyncSession, user: User, payment: dict) -> bool:
    """Записывает подтверждённый донат. Идемпотентен по payment_id."""
    from app.services.donations import record_donation

    amount_raw = ((payment.get("amount") or {}).get("value")) or "0"
    try:
        amount_rub = _amount_to_rub(amount_raw, payment.get("id"))
    except (TypeError, ValueError):
        logger.error("Донат %s: не разобрал сумму %r", payment.get("id"), amount_raw)
        return False
    if amount_rub <= 0:
        logger.error("Донат %s: неположительная сумма %s", payment.get("id"), amount_rub)
        return False

    # Анонимность человек выбирает до оплаты, и она едет в метаданных платежа:
    # своего хранилища для «намерения заплатить» у нас нет, а после редиректа на
    # кассу FSM бота уже не при делах.
    anonymous = str((payment.get("metadata") or {}).get("anonymous", "")) == "1"
    donation = await record_donation(
        session, user.id, amount_rub, payment["id"], is_anonymous=anonymous
    )
    if donation is None:
        return True  # повторное уведомление — уже учтён
    logger.info("Донат user=%s на %s ₽ (payment=%s)", user.id, amount_rub, payment["id"])
    # Фиксируем ДО обращений к Telegram: дальше идут сетевые вызовы на секунды,
    # и запись о деньгах не должна ждать, пока они закончатся.
    await session.commit()
    from app.services.goal_events import after_donation

    await after_donation(session, donation)
    await _notify_donation(session, user, amount_rub)
    return True


async def _notify_donation(session: AsyncSession, user: User, amount_rub: int) -> None:
    """Спасибо донатеру и строка владельцу. Сбой уведомления не отменяет донат.

    ⚠️ Всё внутри try: донат уже записан и подтверждён кассой, а вебхуку нужно
    ответить 200. Упасть здесь значит заставить ЮKassa ретраить уведомление по
    уже учтённому платежу — и так до отключения вебхука.
    """
    from app.i18n import t
    from app.services.donations import display_name, user_rank, user_total
    from app.services.telegram_send import send_message
    from app.services.users import user_language

    try:
        total = await user_total(session, user.id)
        rank = await user_rank(session, user.id)
        lang = user_language(user)
        await send_message(
            user.telegram_id,
            t("donate.thanks", lang).format(
                amount=amount_rub,
                total=f"{total:,}".replace(",", " "),
                rank=rank or 1,
            ),
        )
    except Exception:  # noqa: BLE001 — см. комментарий выше
        logger.exception("Не удалось поблагодарить донатера user=%s", user.id)

    # Владельцу — дежурному админу, если назначен, иначе первому из ADMIN_IDS.
    # health_alert_id уже реализует ровно это правило, второй такой же строкой
    # они бы разъехались при следующей правке.
    recipient = settings.health_alert_id
    if not recipient:
        return
    try:
        await send_message(
            int(recipient),
            f"❤️ Донат {amount_rub} ₽ от {display_name(user)} (tg={user.telegram_id})",
        )
    except Exception:  # noqa: BLE001
        logger.exception("Не удалось уведомить владельца о донате")


async def apply_refund(session: AsyncSession, payment_id: str) -> bool:
    """Деньги по платежу ушли обратно — снимаем донат с рейтинга.

    Сами возвраты мы не делаем (решение владельца, это записано в правилах), но
    чарджбэк начинает банк плательщика, и правилами его не запретить. Premium
    здесь намеренно не трогаем: отзыв уже выданной услуги — отдельное решение,
    и принимать его молча в обработчике вебхука неправильно.
    """
    from app.services.donations import mark_refunded

    return await mark_refunded(session, payment_id)

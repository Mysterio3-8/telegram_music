"""Приём TON через Wallet Pay — магазинный API официального кошелька Telegram.

Деньги падают на баланс владельца в @wallet. От опроса блокчейна это отличается
тем, что нам не надо ни искать платёж по комментарию, ни держать свой кошелёк:
кошелёк держит Telegram, а нам приходит уведомление.

🔴 **КОНТРАКТ С ЖИВЫМ API ЗДЕСЬ НЕ ПРОВЕРЕН.** Документация Wallet Pay
рендерится скриптом и из рабочего окружения недоступна, поэтому имена полей
взяты из общего знания об этом API, а не подтверждены запросом. Прежде чем
кнопка появится у людей, обязателен прогон:

    python -m app.cli.walletpay probe --amount 10

Он создаёт настоящий заказ на минимальную сумму, печатает ответ целиком и
показывает, где ожидание разошлось с действительностью. Пока проба не пройдена,
`is_configured()` возвращает False даже при заданном ключе — кнопку человек не
увидит (см. WALLET_PAY_VERIFIED).

⚠️ Курс TON→рубли берётся из `ton_rub_per_ton` и записывается ВМЕСТЕ с донатом.
Прогресс цели фиксируется в рублях на момент оплаты: пересчитывай мы его по
текущему курсу, «собрано 80%» назавтра превращалось бы в «собрано 70%».
"""
import base64
import hashlib
import hmac
import logging
import uuid

import aiohttp

from app.config import settings

logger = logging.getLogger(__name__)

API_BASE = "https://pay.wallet.tg/wpay/store-api/v1"
ORDER_PATH = "/order"
PREVIEW_PATH = "/order/preview"
AUTH_HEADER = "Wpay-Store-Api-Key"
TIMEOUT_SEC = 20
# Заказ живёт три часа: дольше держать бессмысленно — курс уедет, а человек,
# который не заплатил за три часа, уже не заплатит по этой ссылке.
ORDER_TIMEOUT_SEC = 3 * 60 * 60
NANO_PER_TON = 1_000_000_000


def is_configured() -> bool:
    """Готовы ли принимать TON.

    Курс обязателен наравне с ключом: без него нечем перевести рубли в TON, а
    просить у человека «сколько не жалко в TON» и класть в цель случайное число
    рублей — это врать в прогрессе.
    """
    return bool(
        settings.wallet_pay_api_key
        and settings.ton_rub_per_ton > 0
        # См. предупреждение в докстринге модуля: пока проба не пройдена и флаг
        # не выставлен вручную, способ оплаты остаётся скрытым.
        and settings.wallet_pay_verified
    )


def ton_for_rub(amount_rub: int) -> float:
    """Сколько TON просить за нужную сумму в рублях.

    ⚠️ Округление ВВЕРХ до 9 знаков не делаем и вниз тоже: берём обычное
    округление до 4 знаков — этого хватает, а лишние знаки в сумме на экране
    выглядят как ошибка.
    """
    if settings.ton_rub_per_ton <= 0:
        raise ValueError("Курс TON не задан (TON_RUB_PER_TON)")
    return round(amount_rub / settings.ton_rub_per_ton, 4)


def rub_for_nano(nano: int) -> int:
    """Нанотоны обратно в рубли — по курсу из настроек, целыми рублями."""
    if settings.ton_rub_per_ton <= 0:
        return 0
    return int(round(nano / NANO_PER_TON * settings.ton_rub_per_ton))


def _headers() -> dict[str, str]:
    return {
        AUTH_HEADER: settings.wallet_pay_api_key,
        "Content-Type": "application/json",
    }


async def create_order(
    telegram_id: int, amount_rub: int, *, anonymous: bool = False, force: bool = False
) -> tuple[str, str] | None:
    """Создать заказ. Возвращает (external_id, ссылка на оплату) или None.

    `external_id` наш собственный и становится `payment_id` доната — тем самым
    ключом идемпотентности, по которому повторное уведомление не удвоит вклад.
    Свой id, а не их, потому что записать его надо ДО того, как мы узнаем их id.
    """
    # force — только для пробы: она обязана уметь сходить в API ДО того, как
    # предохранитель снят, иначе снять его было бы нечем (курица и яйцо).
    ready = bool(settings.wallet_pay_api_key and settings.ton_rub_per_ton > 0)
    if not (is_configured() or (force and ready)):
        return None

    external_id = f"donate-{uuid.uuid4().hex[:24]}"
    payload = {
        "amount": {"currencyCode": "TON", "amount": f"{ton_for_rub(amount_rub)}"},
        "description": f"Поддержка проекта — {amount_rub} ₽",
        "externalId": external_id,
        "timeoutSeconds": ORDER_TIMEOUT_SEC,
        "customerTelegramUserId": telegram_id,
        # customData возвращается в уведомлении и переживает весь путь оплаты —
        # это единственное место, где доедет выбор «анонимно» и сумма в рублях,
        # зафиксированная по курсу на момент создания заказа.
        "customData": f"anon={'1' if anonymous else '0'};rub={amount_rub}",
        "returnUrl": f"https://t.me/{settings.bot_username}",
        "failReturnUrl": f"https://t.me/{settings.bot_username}",
    }
    try:
        timeout = aiohttp.ClientTimeout(total=TIMEOUT_SEC)
        async with aiohttp.ClientSession(timeout=timeout) as http:
            async with http.post(
                f"{API_BASE}{ORDER_PATH}", json=payload, headers=_headers()
            ) as response:
                body = await response.json(content_type=None)
                if response.status != 200:
                    logger.error("Wallet Pay create order %s: %s", response.status, body)
                    return None
    except aiohttp.ClientError:
        logger.exception("Wallet Pay недоступен (create order)")
        return None

    link = _extract_pay_link(body)
    if link is None:
        # Ровно тот случай, ради которого написана проба: ключ принят, заказ
        # создан, а ответ не той формы, которую мы ждём.
        logger.error("Wallet Pay: в ответе нет ссылки на оплату. Ответ: %s", body)
        return None
    return external_id, link


def _extract_pay_link(body: dict) -> str | None:
    """Вытащить ссылку оплаты, не полагаясь на одну-единственную форму ответа.

    Терпимость здесь намеренная: контракт не проверен живым запросом, и жёсткое
    `body["data"]["payLink"]` упало бы с KeyError вместо внятной записи в журнал.
    """
    data = body.get("data") if isinstance(body, dict) else None
    for source in (data, body):
        if not isinstance(source, dict):
            continue
        for key in ("payLink", "directPayLink", "pay_link", "url"):
            value = source.get(key)
            if isinstance(value, str) and value.startswith("http"):
                return value
    return None


def verify_signature(
    method: str, uri_path: str, timestamp: str, raw_body: bytes, signature: str
) -> bool:
    """Проверка подписи уведомления Wallet Pay.

    Подписывается строка «МЕТОД.путь.метка времени.тело в base64», ключ — тот же
    магазинный ключ. Сравнение через compare_digest: обычное `==` сравнивает
    строки посимвольно и по времени отказа выдаёт, сколько символов совпало.

    ⚠️ Как и всё в этом модуле, формула не подтверждена живым уведомлением.
    Вебхук при неудачной проверке НЕ зачисляет донат и пишет в журнал и
    ожидаемую, и пришедшую подпись — по этой записи формулу можно поправить,
    не потеряв ни одного платежа: Wallet Pay повторяет уведомление.
    """
    if not settings.wallet_pay_api_key:
        return False
    base = ".".join(
        [
            method.upper(),
            uri_path,
            timestamp,
            base64.b64encode(raw_body).decode(),
        ]
    )
    digest = hmac.new(
        settings.wallet_pay_api_key.encode(), base.encode(), hashlib.sha256
    ).digest()
    expected = base64.b64encode(digest).decode()
    return hmac.compare_digest(expected, signature or "")


async def get_order_status(order_id: str) -> dict | None:
    """Состояние заказа. Нужно пробе и на случай, если уведомление потерялось."""
    if not settings.wallet_pay_api_key:
        return None
    try:
        timeout = aiohttp.ClientTimeout(total=TIMEOUT_SEC)
        async with aiohttp.ClientSession(timeout=timeout) as http:
            async with http.get(
                f"{API_BASE}{PREVIEW_PATH}", params={"id": order_id}, headers=_headers()
            ) as response:
                body = await response.json(content_type=None)
                if response.status != 200:
                    logger.error("Wallet Pay preview %s: %s", response.status, body)
                    return None
                return body
    except aiohttp.ClientError:
        logger.exception("Wallet Pay недоступен (preview)")
        return None


def parse_custom_data(raw: str | None) -> tuple[bool, int | None]:
    """«anon=1;rub=300» → (True, 300). Мусор на входе не должен ронять вебхук."""
    anonymous = False
    amount_rub: int | None = None
    for part in (raw or "").split(";"):
        key, _, value = part.partition("=")
        if key == "anon":
            anonymous = value == "1"
        elif key == "rub" and value.isascii() and value.isdigit():
            amount_rub = int(value)
    return anonymous, amount_rub


def extract_order(body: dict) -> dict:
    """Полезная часть уведомления. Форма ответа не подтверждена — берём терпимо."""
    if not isinstance(body, dict):
        return {}
    payload = body.get("payload")
    if isinstance(payload, dict):
        return payload
    data = body.get("data")
    if isinstance(data, dict):
        return data
    return body


def order_is_paid(order: dict) -> bool:
    """Оплачен ли заказ. Проверяем ЯВНО по слову PAID, а не «не FAILED»:
    неизвестный статус должен считаться неоплаченным, иначе опечатка в их API
    зачислит донат, которого не было."""
    status = str(order.get("status") or order.get("orderStatus") or "").upper()
    return status == "PAID"


def order_nano(order: dict) -> int | None:
    """Сколько нанотонов пришло. None — в уведомлении суммы нет."""
    for source in (order.get("amount"), order.get("paymentAmount"), order):
        if not isinstance(source, dict):
            continue
        raw = source.get("amount") or source.get("value")
        if raw is None:
            continue
        try:
            return int(round(float(raw) * NANO_PER_TON))
        except (TypeError, ValueError):
            continue
    return None


async def apply_paid_order(session, order: dict) -> bool:
    """Зачесть оплаченный заказ как донат. Идемпотентно по externalId.

    ⚠️ Сумма в рублях берётся из customData, зафиксированной при СОЗДАНИИ
    заказа, а не пересчитывается по текущему курсу. Иначе один и тот же донат
    давал бы разный вклад в цель в зависимости от того, когда обработали
    уведомление, — а Wallet Pay повторяет их часами.
    """
    from app.services.donations import is_allowed_amount, record_donation
    from app.services.goal_events import after_donation
    from app.services.users import get_user_by_telegram_id

    if not order_is_paid(order):
        return False

    external_id = order.get("externalId") or order.get("external_id")
    if not external_id:
        logger.error("Wallet Pay: уведомление без externalId: %s", order)
        return False

    telegram_raw = order.get("customerTelegramUserId") or order.get("customer_telegram_user_id")
    if not telegram_raw or not str(telegram_raw).isdigit():
        logger.error("Wallet Pay %s: нет telegram id покупателя", external_id)
        return False

    user = await get_user_by_telegram_id(session, int(telegram_raw))
    if user is None:
        logger.error("Wallet Pay %s: пользователь tg=%s не найден", external_id, telegram_raw)
        return False

    anonymous, amount_rub = parse_custom_data(
        order.get("customData") or order.get("custom_data")
    )
    nano = order_nano(order)
    if amount_rub is None:
        # Запасной путь: в customData суммы не оказалось — считаем по курсу.
        # Хуже фиксации, но лучше, чем потерять донат целиком.
        amount_rub = rub_for_nano(nano or 0)
        logger.warning(
            "Wallet Pay %s: суммы в customData нет, пересчитал по текущему курсу → %s ₽",
            external_id,
            amount_rub,
        )
    if amount_rub <= 0 or not is_allowed_amount(amount_rub):
        logger.error("Wallet Pay %s: недопустимая сумма %s ₽", external_id, amount_rub)
        return False

    donation = await record_donation(
        session,
        user.id,
        amount_rub,
        str(external_id),
        provider="walletpay",
        is_anonymous=anonymous,
        ton_nano=nano,
        rub_per_ton=settings.ton_rub_per_ton or None,
    )
    if donation is None:
        return True  # повторное уведомление — уже учтён

    logger.info(
        "Донат TON user=%s на %s ₽ (%s нанотон, заказ %s)",
        user.id,
        amount_rub,
        nano,
        external_id,
    )
    await session.commit()
    await after_donation(session, donation)
    return True

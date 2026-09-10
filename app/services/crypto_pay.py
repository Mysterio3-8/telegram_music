"""Приём TON через Crypto Pay — платёжный API @CryptoBot.

Почему именно он, а не два других пути, с которых начинали:

- **Wallet Pay** (@wallet) — его документация рендерится скриптом и из окружения
  разработки недоступна, то есть контракт пришлось бы угадывать. Код под него
  удалён: держать в проекте платёжный модуль, написанный по догадке, опаснее,
  чем не иметь его вовсе.
- **Прямой перевод на кошелёк** ([ton_donations.py](app/services/ton_donations.py))
  работает без единого ключа и остаётся запасным путём, но требует от человека
  скопировать адрес и метку, а от нас — опрашивать блокчейн по таймеру.

Здесь же есть и точная спецификация, и вебхук с проверяемой подписью.

⚠️ **Счёт выставляется в РУБЛЯХ** (`currency_type=fiat`, `fiat=RUB`,
`accepted_assets=TON`). Это важнее, чем кажется: курс считает Crypto Pay в
момент оплаты, и наш собственный `TON_RUB_PER_TON` в этой ветке не участвует
вовсе. Значит, в прогресс цели попадает ровно та рублёвая сумма, которую человек
и собирался дать, — без расхождения между «попросили» и «пришло».

Деньги падают на баланс приложения в @CryptoBot; вывести их на свой кошелёк
владелец может оттуда.
"""
import hashlib
import hmac
import logging

import aiohttp

from app.config import settings

logger = logging.getLogger(__name__)

API_BASE = "https://pay.crypt.bot/api"
AUTH_HEADER = "Crypto-Pay-API-Token"
SIGNATURE_HEADER = "crypto-pay-api-signature"
TIMEOUT_SEC = 20
# Счёт живёт три часа. Дольше держать незачем: человек, не заплативший за это
# время, уже не заплатит по этой ссылке, а висящие счета мешают читать список.
INVOICE_TTL_SEC = 3 * 60 * 60


def is_configured() -> bool:
    return bool(settings.crypto_pay_token)


async def _call(method: str, params: dict | None = None) -> dict | None:
    """Вызов API. None — не получилось; причина уже в журнале."""
    if not is_configured():
        return None
    try:
        timeout = aiohttp.ClientTimeout(total=TIMEOUT_SEC)
        async with aiohttp.ClientSession(timeout=timeout) as http:
            async with http.post(
                f"{API_BASE}/{method}",
                json=params or {},
                headers={AUTH_HEADER: settings.crypto_pay_token},
            ) as response:
                body = await response.json(content_type=None)
                if response.status != 200 or not body.get("ok"):
                    # В `error` у них лежит внятный код вроде
                    # PARAM_SHORT_NAME_REQUIRED — тащим его в журнал целиком.
                    logger.error(
                        "Crypto Pay %s %s: %s", method, response.status, (body or {}).get("error")
                    )
                    return None
                return body.get("result")
    except aiohttp.ClientError:
        logger.exception("Crypto Pay недоступен (%s)", method)
        return None


async def get_me() -> dict | None:
    """Проверка токена. Ею пользуется команда-проба."""
    return await _call("getMe")


def _payload(telegram_id: int, anonymous: bool) -> str:
    """Наши данные, которые Crypto Pay вернёт вместе с оплаченным счётом.

    Своего хранилища «ожидаемых платежей» не заводим: счёт может быть оплачен
    через час или не оплачен вовсе, и такие записи копились бы мусором. Подпись
    здесь не нужна — в отличие от комментария к переводу, это поле заполняем МЫ,
    и обратно оно приходит от Crypto Pay, а не от человека.
    """
    return f"{telegram_id}:{1 if anonymous else 0}"


def parse_payload(raw: str | None) -> tuple[int, bool] | None:
    """«12345:1» → (12345, True). None — поле пустое или испорчено."""
    if not raw:
        return None
    user_raw, _, anon_raw = str(raw).partition(":")
    # isascii рядом с isdigit: «²» проходит isdigit(), но int() на нём падает.
    if not (user_raw.isascii() and user_raw.isdigit()):
        return None
    return int(user_raw), anon_raw == "1"


async def create_invoice(
    telegram_id: int, amount_rub: int, *, anonymous: bool = False
) -> tuple[str, str] | None:
    """Счёт на сумму В РУБЛЯХ, оплачиваемый в TON.

    Возвращает (id счёта, ссылка на оплату) или None.
    """
    from app.services.donations import is_allowed_amount

    # Вторая проверка суммы у самой границы с деньгами: первая стоит в хендлере,
    # но между ними FSM и callback_data, а цена ошибки здесь — реальный платёж.
    if not is_allowed_amount(amount_rub):
        logger.error("Crypto Pay: сумма %s вне допустимых границ", amount_rub)
        return None

    result = await _call(
        "createInvoice",
        {
            "currency_type": "fiat",
            "fiat": "RUB",
            "amount": str(amount_rub),
            # Только TON: остальные монеты владелец не просил, а лишний выбор на
            # экране оплаты — лишний повод передумать.
            "accepted_assets": "TON",
            "description": f"Поддержка проекта — {amount_rub} ₽",
            "payload": _payload(telegram_id, anonymous),
            "expires_in": INVOICE_TTL_SEC,
            "paid_btn_name": "openBot",
            "paid_btn_url": f"https://t.me/{settings.bot_username}",
            # Комментарий к оплате нам не нужен и только путал бы: всё, что важно,
            # уже лежит в payload.
            "allow_comments": False,
        },
    )
    if not result:
        return None

    invoice_id = result.get("invoice_id")
    # ⚠️ `pay_url` объявлен устаревшим — берём `bot_invoice_url`, но с запасными
    # вариантами: молча отдать None из-за переименования поля значило бы
    # «оплата не работает» без единого следа в журнале.
    link = (
        result.get("bot_invoice_url")
        or result.get("mini_app_invoice_url")
        or result.get("pay_url")
    )
    if not invoice_id or not link:
        logger.error("Crypto Pay: в ответе нет id счёта или ссылки. Ответ: %s", result)
        return None
    return str(invoice_id), str(link)


def verify_signature(raw_body: bytes, signature: str) -> bool:
    """Подпись уведомления: HMAC-SHA256 тела, ключ — SHA256 от токена.

    ⚠️ Подписывается СЫРОЕ тело запроса, а не разобранный и заново собранный
    JSON: порядок ключей и пробелы после повторной сборки почти наверняка
    разойдутся с оригиналом, и подпись перестанет сходиться на ровном месте.

    Сравнение через compare_digest: обычное `==` сравнивает строки посимвольно и
    по времени отказа выдаёт, сколько символов совпало.
    """
    if not is_configured():
        return False
    secret = hashlib.sha256(settings.crypto_pay_token.encode()).digest()
    expected = hmac.new(secret, raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, (signature or "").strip())


def invoice_is_paid(invoice: dict) -> bool:
    """Оплачен ли счёт. Проверяем ЯВНО по слову paid, а не «не active»:
    неизвестный статус обязан считаться неоплаченным."""
    return str(invoice.get("status") or "").lower() == "paid"


def invoice_amount_rub(invoice: dict) -> int | None:
    """Рублёвая сумма счёта. None — разобрать не удалось.

    Берём `amount`: у счёта с `currency_type=fiat` это и есть сумма в рублях,
    ради которой всё и затевалось. `paid_amount` — сколько TON человек отдал, и
    в прогресс цели оно не идёт.
    """
    try:
        value = float(invoice.get("amount"))
    except (TypeError, ValueError):
        return None
    rub = int(round(value))
    return rub if rub > 0 else None


def invoice_nano(invoice: dict) -> int | None:
    """Сколько нанотонов реально заплачено — только для истории в базе."""
    if str(invoice.get("paid_asset") or invoice.get("asset") or "").upper() != "TON":
        return None
    try:
        return int(round(float(invoice.get("paid_amount")) * 1_000_000_000))
    except (TypeError, ValueError):
        return None


async def get_invoice(invoice_id: str) -> dict | None:
    """Один счёт по id — для перепроверки и на случай потерянного уведомления."""
    result = await _call("getInvoices", {"invoice_ids": str(invoice_id)})
    items = (result or {}).get("items") if isinstance(result, dict) else result
    if not items:
        return None
    return items[0]


async def apply_paid_invoice(session, invoice: dict) -> bool:
    """Зачесть оплаченный счёт как донат. Идемпотентно по id счёта.

    ⚠️ Возврат True при повторе обязателен: Crypto Pay повторяет уведомление до
    17 раз за трое суток и ОТКЛЮЧАЕТ вебхук, если эндпоинт так и не ответил.
    """
    from app.services.donations import record_donation
    from app.services.goal_events import after_donation
    from app.services.users import get_user_by_telegram_id

    if not invoice_is_paid(invoice):
        return False

    invoice_id = invoice.get("invoice_id")
    if not invoice_id:
        logger.error("Crypto Pay: уведомление без invoice_id: %s", invoice)
        return False

    parsed = parse_payload(invoice.get("payload"))
    if parsed is None:
        logger.error("Crypto Pay %s: payload не разобран (%r)", invoice_id, invoice.get("payload"))
        return False
    telegram_id, anonymous = parsed

    user = await get_user_by_telegram_id(session, telegram_id)
    if user is None:
        logger.error("Crypto Pay %s: пользователь tg=%s не найден", invoice_id, telegram_id)
        return False

    amount_rub = invoice_amount_rub(invoice)
    if amount_rub is None:
        logger.error("Crypto Pay %s: не разобрал сумму %r", invoice_id, invoice.get("amount"))
        return False

    donation = await record_donation(
        session,
        user.id,
        amount_rub,
        f"cryptopay-{invoice_id}",
        provider="cryptopay",
        is_anonymous=anonymous,
        ton_nano=invoice_nano(invoice),
    )
    if donation is None:
        return True  # повторное уведомление — уже учтён

    await session.commit()
    logger.info("Донат TON (Crypto Pay): user=%s %s ₽, счёт %s", user.id, amount_rub, invoice_id)
    await after_donation(session, donation)
    return True

"""Донаты в TON напрямую на кошелёк владельца.

Человек переводит TON на адрес из настроек, указывая в комментарии короткую
подписанную метку. Мы опрашиваем публичный API блокчейна, находим приход с этой
меткой и засчитываем донат.

Почему так, а не через Wallet Pay: **этот путь проверяем**. Форма ответа
toncenter снята живым запросом (`result[].in_msg` с `source`, `value`,
`message`), тогда как документация Wallet Pay из окружения разработки
недоступна. Посредника здесь нет вовсе — деньги идут сразу на кошелёк владельца.

⚠️ **Метка самодостаточна и ничего не хранит.** В ней зашиты id человека, курс
на момент запроса и флаг анонимности, всё под HMAC — тем же приёмом, что в
[candidate_ref.py](app/services/candidate_ref.py). Отдельная таблица «ожидаемых
платежей» не нужна: перевод может прийти через час, через сутки или не прийти
вовсе, и хранить такие записи значило бы копить мусор, который никто не чистит.

⚠️ **Засчитывается то, что РЕАЛЬНО пришло**, а не то, что человек собирался
отправить. Сумма в рублях считается по курсу из метки (он зафиксирован в момент
запроса) и по фактическим нанотонам. Иначе недоплата давала бы полный вклад в
цель, а переплата — урезанный.
"""
import base64
import hashlib
import hmac
import logging

import aiohttp

from app.config import settings

logger = logging.getLogger(__name__)

TONCENTER_API = "https://toncenter.com/api/v2"
TIMEOUT_SEC = 20
NANO_PER_TON = 1_000_000_000
# Сколько последних транзакций смотреть за один проход. Своего курсора мы не
# держим намеренно: идемпотентность даёт хэш транзакции, а полсотни записей на
# нашем обороте с запасом перекрывают любой разумный простой опроса.
SCAN_LIMIT = 50
# Метка вида «im.<данные>.<подпись>». Короткая: комментарий человек видит в
# кошельке, и простыня из ста символов выглядит как мошенничество.
MEMO_PREFIX = "im"
SIG_LENGTH = 10


def is_configured() -> bool:
    """Готовы ли принимать TON: нужен адрес и курс.

    Курс обязателен: без него нечем перевести пришедшие тонны в рубли, а класть
    в прогресс цели случайное число — это врать в полосе.
    """
    return bool(settings.ton_wallet_address and settings.ton_rub_per_ton > 0)


def _secret() -> bytes:
    """Ключ подписи меток. Тот же фолбэк, что у остальных подписей проекта."""
    return (settings.jwt_secret or settings.bot_token or "tg-music").encode()


def _sign(payload: str) -> str:
    digest = hmac.new(_secret(), payload.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")[:SIG_LENGTH]


def make_memo(user_id: int, *, anonymous: bool = False, rate: int | None = None) -> str:
    """Метка платежа: «im.<user>-<курс>-<аноним>.<подпись>».

    Подпись обязательна. Без неё любой мог бы приписать чужой донат себе или
    подставить выгодный курс, просто написав нужный комментарий к переводу —
    комментарий человек пишет сам, это не наши данные.
    """
    rub_per_ton = rate if rate is not None else settings.ton_rub_per_ton
    payload = f"{user_id}-{rub_per_ton}-{1 if anonymous else 0}"
    return f"{MEMO_PREFIX}.{payload}.{_sign(payload)}"


def parse_memo(comment: str | None) -> tuple[int, int, bool] | None:
    """Метка → (user_id, курс, аноним). None — не наша метка или подпись не сошлась."""
    if not comment:
        return None
    parts = comment.strip().split(".")
    if len(parts) != 3 or parts[0] != MEMO_PREFIX:
        return None
    _, payload, signature = parts
    if not hmac.compare_digest(_sign(payload), signature):
        logger.warning("TON: метка с неверной подписью: %r", comment[:60])
        return None
    fields = payload.split("-")
    if len(fields) != 3:
        return None
    user_raw, rate_raw, anon_raw = fields
    # isascii рядом с isdigit: «²» проходит isdigit(), но int() на нём падает.
    if not all(f.isascii() and f.isdigit() for f in (user_raw, rate_raw, anon_raw)):
        return None
    rate = int(rate_raw)
    if rate <= 0:
        return None
    return int(user_raw), rate, anon_raw == "1"


def ton_for_rub(amount_rub: int) -> float:
    """Сколько TON просить за нужную сумму в рублях."""
    if settings.ton_rub_per_ton <= 0:
        raise ValueError("Курс TON не задан (TON_RUB_PER_TON)")
    return round(amount_rub / settings.ton_rub_per_ton, 4)


def rub_for_nano(nano: int, rate: int) -> int:
    """Пришедшие нанотоны → рубли по курсу из метки, целыми рублями вниз.

    Вниз, а не обычным округлением: округление вверх приписало бы человеку рубль,
    которого он не переводил, а в сумме по многим донатам это расхождение с
    кошельком владельца.
    """
    if rate <= 0:
        return 0
    return int(nano * rate // NANO_PER_TON)


def transfer_link(amount_ton: float, memo: str) -> str:
    """Ссылка, открывающая кошелёк с подставленными адресом, суммой и меткой.

    ⚠️ Это УДОБСТВО, а не единственный путь. Сработает ли конкретный кошелёк по
    такой ссылке, снаружи не проверить, поэтому на экране рядом всегда лежат
    адрес, сумма и метка отдельными строками для копирования: этот путь работает
    у всех и проверяется целиком нами.
    """
    nano = int(round(amount_ton * NANO_PER_TON))
    address = settings.ton_wallet_address
    return f"https://app.tonkeeper.com/transfer/{address}?amount={nano}&text={memo}"


async def fetch_incoming(limit: int = SCAN_LIMIT) -> list[dict] | None:
    """Последние транзакции кошелька. None — API недоступен (это НЕ «нет денег»).

    Разница принципиальна: пустой список означает «приходов нет», а None —
    «спросить не удалось». Смешай их, и сбой сети выглядел бы как отсутствие
    платежа, о чём человеку сказали бы «мы ничего не получили».
    """
    if not settings.ton_wallet_address:
        return None
    params = {
        "address": settings.ton_wallet_address,
        "limit": str(limit),
    }
    if settings.toncenter_api_key:
        params["api_key"] = settings.toncenter_api_key
    try:
        timeout = aiohttp.ClientTimeout(total=TIMEOUT_SEC)
        async with aiohttp.ClientSession(timeout=timeout) as http:
            async with http.get(f"{TONCENTER_API}/getTransactions", params=params) as response:
                body = await response.json(content_type=None)
                if response.status != 200 or not body.get("ok"):
                    logger.error("toncenter %s: %s", response.status, body)
                    return None
                return body.get("result") or []
    except aiohttp.ClientError:
        logger.exception("toncenter недоступен")
        return None


def extract_payment(tx: dict) -> tuple[str, int, str] | None:
    """Транзакция → (хэш, нанотоны, комментарий). None — это не входящий перевод.

    Отсеиваем всё, что переводом не является: исходящие сообщения, служебные
    внешние (у них пустой `source`) и нулевые суммы. Именно так выглядит первая
    транзакция любого кошелька — его развёртывание.
    """
    in_msg = tx.get("in_msg") or {}
    source = in_msg.get("source")
    if not source:
        return None
    raw_value = in_msg.get("value")
    try:
        nano = int(raw_value)
    except (TypeError, ValueError):
        return None
    if nano <= 0:
        return None
    tx_hash = (tx.get("transaction_id") or {}).get("hash") or in_msg.get("hash")
    if not tx_hash:
        return None
    return str(tx_hash), nano, str(in_msg.get("message") or "")


async def collect(session) -> int:
    """Разобрать свежие приходы и зачесть донаты. Возвращает число новых.

    Идемпотентность держится на хэше транзакции: он уникален в блокчейне и
    ложится в `donations.payment_id`, у которого уникальный индекс. Поэтому
    повторный проход по тем же пятидесяти транзакциям безвреден, и своего
    курсора не нужно.
    """
    from app.services.donations import record_donation
    from app.services.goal_events import after_donation
    from app.services.users import get_user_by_telegram_id

    if not is_configured():
        return 0

    transactions = await fetch_incoming()
    if transactions is None:
        return 0

    counted = 0
    # Свежие идут первыми — разворачиваем, чтобы засчитывать в порядке прихода.
    for tx in reversed(transactions):
        payment = extract_payment(tx)
        if payment is None:
            continue
        tx_hash, nano, comment = payment
        parsed = parse_memo(comment)
        if parsed is None:
            # Перевод без нашей метки: деньги пришли, но чей это донат — неизвестно.
            # Молча выбрасывать нельзя, поэтому пишем в журнал: по нему владелец
            # сможет разобраться руками.
            logger.warning(
                "TON: приход %s нанотон без опознаваемой метки (комментарий %r)",
                nano,
                comment[:60],
            )
            continue

        telegram_id, rate, anonymous = parsed
        user = await get_user_by_telegram_id(session, telegram_id)
        if user is None:
            logger.error("TON: метка ведёт на неизвестного пользователя tg=%s", telegram_id)
            continue

        amount_rub = rub_for_nano(nano, rate)
        if amount_rub <= 0:
            logger.warning("TON: приход %s нанотон по курсу %s дал 0 ₽ — пропускаю", nano, rate)
            continue

        donation = await record_donation(
            session,
            user.id,
            amount_rub,
            f"ton-{tx_hash}",
            provider="ton",
            is_anonymous=anonymous,
            ton_nano=nano,
            rub_per_ton=rate,
        )
        if donation is None:
            continue  # этот приход уже зачтён на прошлом проходе

        await session.commit()
        logger.info(
            "Донат TON: user=%s %s ₽ (%s нанотон, tx %s)", user.id, amount_rub, nano, tx_hash
        )
        await after_donation(session, donation)
        counted += 1

    return counted

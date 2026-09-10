"""TON-донаты: Crypto Pay и прямой перевод на кошелёк.

Через оба пути идут деньги, а живой платёж до выката не проведёшь. Поэтому
тесты стерегут ровно то, что можно проверить без сети: подписи и метки нельзя
подделать, подсчёт рублей честный, повтор уведомления не удваивает вклад, а
мусор на входе не роняет обработку.
"""
import hashlib
import hmac
import json

import pytest
from sqlalchemy import select

from app.config import settings
from app.db.models import Donation, User
from app.services import crypto_pay, ton_donations


async def _noop(*args, **kwargs) -> None:
    return None


async def _user(session, telegram_id: int = 555) -> User:
    user = User(telegram_id=telegram_id, username="tonfan")
    session.add(user)
    await session.flush()
    return user


@pytest.fixture
def wallet_ready(monkeypatch):
    monkeypatch.setattr(settings, "ton_wallet_address", "UQtest", raising=False)
    monkeypatch.setattr(settings, "ton_rub_per_ton", 300, raising=False)
    monkeypatch.setattr(settings, "jwt_secret", "secret", raising=False)


@pytest.fixture
def crypto_ready(monkeypatch):
    monkeypatch.setattr(settings, "crypto_pay_token", "12345:AAtest", raising=False)


@pytest.fixture
def quiet_goals(monkeypatch):
    monkeypatch.setattr("app.services.goal_events.after_donation", _noop, raising=False)


# =========================== прямой перевод =================================

def test_wallet_not_configured_without_address(monkeypatch):
    monkeypatch.setattr(settings, "ton_wallet_address", "", raising=False)
    monkeypatch.setattr(settings, "ton_rub_per_ton", 300, raising=False)
    assert ton_donations.is_configured() is False


def test_wallet_not_configured_without_rate(monkeypatch):
    """Без курса пришедшие тонны не во что пересчитать — принимать нельзя."""
    monkeypatch.setattr(settings, "ton_wallet_address", "UQtest", raising=False)
    monkeypatch.setattr(settings, "ton_rub_per_ton", 0, raising=False)
    assert ton_donations.is_configured() is False


# --- метка платежа ---

def test_memo_roundtrip(wallet_ready):
    memo = ton_donations.make_memo(555, anonymous=True)
    assert ton_donations.parse_memo(memo) == (555, 300, True)


def test_memo_is_short_enough_to_read(wallet_ready):
    """Метку человек видит в кошельке. Простыня из ста символов выглядит как
    мошенничество, и перевод просто не отправят."""
    assert len(ton_donations.make_memo(123456789)) <= 40


def test_memo_with_broken_signature_is_rejected(wallet_ready):
    """🔴 Комментарий к переводу пишет ЧЕЛОВЕК. Без проверки подписи можно было
    бы приписать себе чужой донат или подставить выгодный курс."""
    memo = ton_donations.make_memo(555)
    forged = memo[:-1] + ("x" if memo[-1] != "x" else "y")
    assert ton_donations.parse_memo(forged) is None


def test_memo_with_forged_rate_is_rejected(wallet_ready):
    """Подставить курс 100000 и получить огромный вклад за копейку — нельзя."""
    body = ton_donations.make_memo(555).split(".")[1]
    user_id, _rate, anon = body.split("-")
    forged = f"im.{user_id}-100000-{anon}.{ton_donations._sign(body)}"
    assert ton_donations.parse_memo(forged) is None


@pytest.mark.parametrize(
    "comment", [None, "", "привет", "im.broken", "im.1-2-3.short", "спасибо за музыку"]
)
def test_parse_memo_survives_garbage(wallet_ready, comment):
    assert ton_donations.parse_memo(comment) is None


def test_memo_from_another_secret_is_rejected(monkeypatch, wallet_ready):
    memo = ton_donations.make_memo(555)
    monkeypatch.setattr(settings, "jwt_secret", "другой-секрет", raising=False)
    assert ton_donations.parse_memo(memo) is None


# --- деньги ---

def test_rub_for_nano_rounds_down(wallet_ready):
    """Вниз, а не по-обычному: округление вверх приписало бы человеку рубль,
    которого он не переводил, и сумма разошлась бы с кошельком владельца."""
    assert ton_donations.rub_for_nano(ton_donations.NANO_PER_TON, 300) == 300
    # 0.999 TON по 300 ₽ = 299.7 ₽ → 299, а не 300.
    assert ton_donations.rub_for_nano(999_000_000, 300) == 299


def test_rub_for_nano_zero_rate(wallet_ready):
    assert ton_donations.rub_for_nano(10**9, 0) == 0


def test_ton_for_rub(wallet_ready):
    assert ton_donations.ton_for_rub(300) == 1.0
    assert ton_donations.ton_for_rub(150) == 0.5


# --- разбор транзакций ---

def _tx(nano: int = 10**9, comment: str = "", source: str = "UQfrom", tx_hash: str = "h1") -> dict:
    return {
        "transaction_id": {"hash": tx_hash},
        "in_msg": {"source": source, "value": str(nano), "message": comment},
    }


def test_extract_payment_reads_transfer():
    assert ton_donations.extract_payment(_tx(500, "im.x")) == ("h1", 500, "im.x")


def test_extract_payment_skips_wallet_deploy():
    """Первая транзакция любого кошелька — его развёртывание: пустой источник и
    нулевая сумма. Засчитать её было бы донатом из ниоткуда."""
    assert ton_donations.extract_payment(_tx(0, "", source="")) is None


def test_extract_payment_skips_zero_and_garbage():
    assert ton_donations.extract_payment(_tx(0)) is None
    assert ton_donations.extract_payment({"in_msg": {"source": "a", "value": "нечисло"}}) is None
    assert ton_donations.extract_payment({}) is None


async def test_collect_records_donation(session, wallet_ready, quiet_goals, monkeypatch):
    await _user(session)
    memo = ton_donations.make_memo(555)
    monkeypatch.setattr(
        ton_donations, "fetch_incoming", lambda limit=50: _returns([_tx(10**9, memo)])
    )
    assert await ton_donations.collect(session) == 1

    donation = (await session.execute(select(Donation))).scalar_one()
    assert donation.amount_rub == 300
    assert donation.provider == "ton"
    assert donation.ton_nano == 10**9


async def test_collect_is_idempotent(session, wallet_ready, quiet_goals, monkeypatch):
    """Курсора мы не держим — каждый проход смотрит те же полсотни транзакций.
    Держит идемпотентность хэш транзакции."""
    await _user(session)
    memo = ton_donations.make_memo(555)
    monkeypatch.setattr(
        ton_donations, "fetch_incoming", lambda limit=50: _returns([_tx(10**9, memo)])
    )
    assert await ton_donations.collect(session) == 1
    assert await ton_donations.collect(session) == 0
    assert len((await session.execute(select(Donation))).scalars().all()) == 1


async def test_collect_counts_what_actually_arrived(
    session, wallet_ready, quiet_goals, monkeypatch
):
    """Человек собирался дать 300 ₽, а отправил полтона. Засчитываем реальные
    150 ₽: иначе недоплата давала бы полный вклад в цель."""
    await _user(session)
    memo = ton_donations.make_memo(555)
    monkeypatch.setattr(
        ton_donations, "fetch_incoming", lambda limit=50: _returns([_tx(500_000_000, memo)])
    )
    await ton_donations.collect(session)
    assert (await session.execute(select(Donation))).scalar_one().amount_rub == 150


async def test_collect_skips_transfer_without_memo(session, wallet_ready, monkeypatch):
    """Приход без метки не приписывается никому — чей он, неизвестно."""
    await _user(session)
    monkeypatch.setattr(
        ton_donations, "fetch_incoming", lambda limit=50: _returns([_tx(10**9, "спасибо")])
    )
    assert await ton_donations.collect(session) == 0
    assert (await session.execute(select(Donation))).scalars().all() == []


async def test_collect_returns_zero_when_blockchain_is_silent(session, wallet_ready, monkeypatch):
    """None от блокчейна — «спросить не удалось», а не «денег нет»."""
    monkeypatch.setattr(ton_donations, "fetch_incoming", lambda limit=50: _returns(None))
    assert await ton_donations.collect(session) == 0


def _returns(value):
    async def _coro():
        return value

    return _coro()


# ============================= Crypto Pay ===================================

def test_crypto_pay_off_without_token(monkeypatch):
    monkeypatch.setattr(settings, "crypto_pay_token", "", raising=False)
    assert crypto_pay.is_configured() is False


def test_crypto_pay_payload_roundtrip():
    assert crypto_pay.parse_payload(crypto_pay._payload(555, True)) == (555, True)
    assert crypto_pay.parse_payload(crypto_pay._payload(555, False)) == (555, False)


@pytest.mark.parametrize("raw", [None, "", "мусор", ":1", "²:1"])
def test_crypto_pay_payload_survives_garbage(raw):
    assert crypto_pay.parse_payload(raw) is None


def _sign(token: str, body: bytes) -> str:
    secret = hashlib.sha256(token.encode()).digest()
    return hmac.new(secret, body, hashlib.sha256).hexdigest()


def test_crypto_pay_signature_accepts_correct(crypto_ready):
    body = json.dumps({"update_type": "invoice_paid"}).encode()
    assert crypto_pay.verify_signature(body, _sign("12345:AAtest", body))


def test_crypto_pay_signature_rejects_tampered_body(crypto_ready):
    """Подпись считается по СЫРОМУ телу — подмена суммы обязана её сломать."""
    good = _sign("12345:AAtest", b'{"amount":"49"}')
    assert not crypto_pay.verify_signature(b'{"amount":"9999"}', good)


def test_crypto_pay_signature_rejects_foreign_token(crypto_ready):
    body = b"{}"
    assert not crypto_pay.verify_signature(body, _sign("чужой-токен", body))


def test_crypto_pay_signature_rejects_empty(crypto_ready):
    assert not crypto_pay.verify_signature(b"{}", "")


@pytest.mark.parametrize("status", ["paid", "PAID", "Paid"])
def test_invoice_is_paid(status):
    assert crypto_pay.invoice_is_paid({"status": status})


@pytest.mark.parametrize("status", ["active", "expired", "", "НЕЧТО_НОВОЕ"])
def test_invoice_not_paid_for_anything_else(status):
    assert not crypto_pay.invoice_is_paid({"status": status})


def test_invoice_amount_is_the_fiat_one():
    """У счёта currency_type=fiat поле amount — это рубли. Именно они идут в
    прогресс цели, а paid_amount (тонны) — только в историю."""
    assert crypto_pay.invoice_amount_rub({"amount": "49", "paid_amount": "0.16"}) == 49


def test_invoice_amount_rejects_garbage():
    assert crypto_pay.invoice_amount_rub({"amount": "нечисло"}) is None
    assert crypto_pay.invoice_amount_rub({"amount": "0"}) is None
    assert crypto_pay.invoice_amount_rub({}) is None


def test_invoice_nano_only_for_ton():
    assert crypto_pay.invoice_nano({"paid_asset": "TON", "paid_amount": "1.5"}) == 1_500_000_000
    assert crypto_pay.invoice_nano({"paid_asset": "USDT", "paid_amount": "1.5"}) is None


def _invoice(**over) -> dict:
    inv = {
        "invoice_id": 9001,
        "status": "paid",
        "amount": "300",
        "paid_asset": "TON",
        "paid_amount": "1.0",
        "payload": "555:0",
    }
    inv.update(over)
    return inv


async def test_apply_paid_invoice_records_donation(session, crypto_ready, quiet_goals):
    await _user(session)
    assert await crypto_pay.apply_paid_invoice(session, _invoice()) is True
    donation = (await session.execute(select(Donation))).scalar_one()
    assert donation.amount_rub == 300
    assert donation.provider == "cryptopay"
    assert donation.ton_nano == 1_000_000_000


async def test_apply_paid_invoice_is_idempotent(session, crypto_ready, quiet_goals):
    """⚠️ Повтор обязан отвечать True: Crypto Pay шлёт уведомление до 17 раз за
    трое суток и ОТКЛЮЧАЕТ вебхук, если эндпоинт так и не ответил."""
    await _user(session)
    assert await crypto_pay.apply_paid_invoice(session, _invoice()) is True
    assert await crypto_pay.apply_paid_invoice(session, _invoice()) is True
    assert len((await session.execute(select(Donation))).scalars().all()) == 1


async def test_apply_paid_invoice_respects_anonymous(session, crypto_ready, quiet_goals):
    await _user(session)
    await crypto_pay.apply_paid_invoice(session, _invoice(payload="555:1"))
    assert (await session.execute(select(Donation))).scalar_one().is_anonymous is True


async def test_unpaid_invoice_is_not_recorded(session, crypto_ready):
    await _user(session)
    assert await crypto_pay.apply_paid_invoice(session, _invoice(status="active")) is False


async def test_invoice_for_unknown_user_is_not_recorded(session, crypto_ready):
    assert await crypto_pay.apply_paid_invoice(session, _invoice()) is False


async def test_invoice_without_payload_is_not_recorded(session, crypto_ready):
    await _user(session)
    assert await crypto_pay.apply_paid_invoice(session, _invoice(payload=None)) is False

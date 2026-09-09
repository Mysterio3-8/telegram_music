"""Wallet Pay: предохранитель, курс, подпись, разбор уведомления.

⚠️ Контракт с живым API Wallet Pay не подтверждён (их документация рендерится
скриптом и недоступна из окружения разработки). Поэтому тесты стерегут ровно то,
что от контракта НЕ зависит: что способ оплаты не включится сам, что деньги
считаются по зафиксированному курсу, что подделанное уведомление отвергается и
что мусор на входе не роняет обработку.
"""
import base64
import hashlib
import hmac

import pytest

from app.config import settings
from app.db.models import User
from app.services import wallet_pay
from app.services.donations import record_donation


@pytest.fixture
def ton_ready(monkeypatch):
    """Ключ и курс заданы, предохранитель снят."""
    monkeypatch.setattr(settings, "wallet_pay_api_key", "test-key", raising=False)
    monkeypatch.setattr(settings, "ton_rub_per_ton", 300, raising=False)
    monkeypatch.setattr(settings, "wallet_pay_verified", True, raising=False)


# --- предохранитель ---------------------------------------------------------

def test_not_configured_without_key(monkeypatch):
    monkeypatch.setattr(settings, "wallet_pay_api_key", "", raising=False)
    monkeypatch.setattr(settings, "ton_rub_per_ton", 300, raising=False)
    monkeypatch.setattr(settings, "wallet_pay_verified", True, raising=False)
    assert wallet_pay.is_configured() is False


def test_not_configured_without_rate(monkeypatch):
    """Без курса нечем перевести рубли в TON — принимать нельзя."""
    monkeypatch.setattr(settings, "wallet_pay_api_key", "k", raising=False)
    monkeypatch.setattr(settings, "ton_rub_per_ton", 0, raising=False)
    monkeypatch.setattr(settings, "wallet_pay_verified", True, raising=False)
    assert wallet_pay.is_configured() is False


def test_key_alone_does_not_enable_ton(monkeypatch):
    """🔴 Главный тест модуля. Контракт не проверен живым запросом, поэтому
    одного ключа мало: пока не пройдена проба и не снят WALLET_PAY_VERIFIED,
    кнопка TON человеку не показывается."""
    monkeypatch.setattr(settings, "wallet_pay_api_key", "k", raising=False)
    monkeypatch.setattr(settings, "ton_rub_per_ton", 300, raising=False)
    monkeypatch.setattr(settings, "wallet_pay_verified", False, raising=False)
    assert wallet_pay.is_configured() is False


def test_configured_when_everything_set(ton_ready):
    assert wallet_pay.is_configured() is True


async def test_create_order_refuses_while_unverified(monkeypatch):
    """Пока предохранитель на месте, заказ не создаётся вовсе — до сети не доходим."""
    monkeypatch.setattr(settings, "wallet_pay_api_key", "k", raising=False)
    monkeypatch.setattr(settings, "ton_rub_per_ton", 300, raising=False)
    monkeypatch.setattr(settings, "wallet_pay_verified", False, raising=False)
    assert await wallet_pay.create_order(1, 100) is None


# --- курс -------------------------------------------------------------------

def test_ton_for_rub(ton_ready):
    assert wallet_pay.ton_for_rub(300) == 1.0
    assert wallet_pay.ton_for_rub(150) == 0.5


def test_ton_for_rub_raises_without_rate(monkeypatch):
    monkeypatch.setattr(settings, "ton_rub_per_ton", 0, raising=False)
    with pytest.raises(ValueError):
        wallet_pay.ton_for_rub(100)


def test_rub_for_nano(ton_ready):
    assert wallet_pay.rub_for_nano(wallet_pay.NANO_PER_TON) == 300
    assert wallet_pay.rub_for_nano(wallet_pay.NANO_PER_TON // 2) == 150


def test_rub_for_nano_zero_rate_does_not_crash(monkeypatch):
    """Деление на ноль в обработке платежа означало бы 500 в ответ кассе."""
    monkeypatch.setattr(settings, "ton_rub_per_ton", 0, raising=False)
    assert wallet_pay.rub_for_nano(10**9) == 0


# --- подпись ----------------------------------------------------------------

def _sign(key: str, method: str, path: str, timestamp: str, body: bytes) -> str:
    base = ".".join([method.upper(), path, timestamp, base64.b64encode(body).decode()])
    return base64.b64encode(
        hmac.new(key.encode(), base.encode(), hashlib.sha256).digest()
    ).decode()


def test_signature_accepts_correct(ton_ready):
    body = b'{"a":1}'
    good = _sign("test-key", "POST", "/webhook/walletpay", "123", body)
    assert wallet_pay.verify_signature("POST", "/webhook/walletpay", "123", body, good)


def test_signature_rejects_tampered_body(ton_ready):
    """Подменили тело — подпись обязана разойтись."""
    good = _sign("test-key", "POST", "/webhook/walletpay", "123", b'{"amount":1}')
    assert not wallet_pay.verify_signature(
        "POST", "/webhook/walletpay", "123", b'{"amount":9999}', good
    )


def test_signature_rejects_foreign_key(ton_ready):
    body = b"{}"
    forged = _sign("someone-elses-key", "POST", "/webhook/walletpay", "123", body)
    assert not wallet_pay.verify_signature("POST", "/webhook/walletpay", "123", body, forged)


def test_signature_rejects_empty(ton_ready):
    assert not wallet_pay.verify_signature("POST", "/webhook/walletpay", "1", b"{}", "")


def test_signature_false_without_key(monkeypatch):
    monkeypatch.setattr(settings, "wallet_pay_api_key", "", raising=False)
    assert not wallet_pay.verify_signature("POST", "/p", "1", b"{}", "whatever")


# --- разбор уведомления -----------------------------------------------------

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("anon=1;rub=300", (True, 300)),
        ("anon=0;rub=49", (False, 49)),
        ("rub=100", (False, 100)),
        ("", (False, None)),
        (None, (False, None)),
        ("мусор", (False, None)),
        ("rub=не-число", (False, None)),
        ("rub=²", (False, None)),  # isdigit() пропускает, int() падает
    ],
)
def test_parse_custom_data(raw, expected):
    assert wallet_pay.parse_custom_data(raw) == expected


@pytest.mark.parametrize("status", ["PAID", "paid", "Paid"])
def test_order_is_paid(status):
    assert wallet_pay.order_is_paid({"status": status})


@pytest.mark.parametrize("status", ["ACTIVE", "EXPIRED", "CANCELLED", "", "UNKNOWN_NEW_STATUS"])
def test_order_not_paid_for_anything_else(status):
    """Неизвестный статус считается НЕоплаченным: опечатка в чужом API не должна
    зачислять донат, которого не было."""
    assert not wallet_pay.order_is_paid({"status": status})


def test_order_nano_reads_amount():
    assert wallet_pay.order_nano({"amount": {"amount": "1.5"}}) == 1_500_000_000


def test_order_nano_returns_none_on_garbage():
    assert wallet_pay.order_nano({"amount": {"amount": "не число"}}) is None
    assert wallet_pay.order_nano({}) is None


def test_extract_order_handles_shapes():
    """Форма уведомления не подтверждена — разбор терпим к трём вариантам."""
    assert wallet_pay.extract_order({"payload": {"id": 1}}) == {"id": 1}
    assert wallet_pay.extract_order({"data": {"id": 2}}) == {"id": 2}
    assert wallet_pay.extract_order({"id": 3}) == {"id": 3}
    assert wallet_pay.extract_order("не словарь") == {}


def test_extract_pay_link_tolerates_shapes():
    assert wallet_pay._extract_pay_link({"data": {"payLink": "https://a"}}) == "https://a"
    assert wallet_pay._extract_pay_link({"directPayLink": "https://b"}) == "https://b"
    assert wallet_pay._extract_pay_link({"data": {"payLink": "не-ссылка"}}) is None
    assert wallet_pay._extract_pay_link({}) is None


# --- зачисление -------------------------------------------------------------

async def _user(session, telegram_id: int) -> User:
    user = User(telegram_id=telegram_id, username="tonfan")
    session.add(user)
    await session.flush()
    return user


def _order(**over) -> dict:
    order = {
        "status": "PAID",
        "externalId": "donate-abc",
        "customerTelegramUserId": 555,
        "customData": "anon=0;rub=300",
        "amount": {"amount": "1.0"},
    }
    order.update(over)
    return order


async def test_apply_paid_order_records_donation(session, ton_ready, monkeypatch):
    monkeypatch.setattr(
        "app.services.goal_events.after_donation", _noop, raising=False
    )
    await _user(session, 555)
    assert await wallet_pay.apply_paid_order(session, _order()) is True

    from app.db.models import Donation
    from sqlalchemy import select

    donation = (await session.execute(select(Donation))).scalar_one()
    assert donation.amount_rub == 300
    assert donation.provider == "walletpay"
    assert donation.ton_nano == 1_000_000_000
    assert donation.rub_per_ton == 300


async def test_apply_paid_order_uses_fixed_rub_not_current_rate(
    session, ton_ready, monkeypatch
):
    """🔴 Курс мог уехать между созданием счёта и уведомлением. Засчитываем то,
    что записано в customData при создании, иначе вклад в цель зависел бы от
    того, когда обработали уведомление."""
    monkeypatch.setattr("app.services.goal_events.after_donation", _noop, raising=False)
    await _user(session, 555)
    monkeypatch.setattr(settings, "ton_rub_per_ton", 999, raising=False)
    await wallet_pay.apply_paid_order(session, _order(customData="anon=0;rub=300"))

    from app.db.models import Donation
    from sqlalchemy import select

    donation = (await session.execute(select(Donation))).scalar_one()
    assert donation.amount_rub == 300  # не 999 за тот же 1 TON


async def test_apply_paid_order_is_idempotent(session, ton_ready, monkeypatch):
    """Wallet Pay повторяет уведомление, пока не получит 200."""
    monkeypatch.setattr("app.services.goal_events.after_donation", _noop, raising=False)
    await _user(session, 555)
    assert await wallet_pay.apply_paid_order(session, _order()) is True
    assert await wallet_pay.apply_paid_order(session, _order()) is True

    from app.db.models import Donation
    from sqlalchemy import select

    assert len((await session.execute(select(Donation))).scalars().all()) == 1


async def test_apply_paid_order_respects_anonymous(session, ton_ready, monkeypatch):
    monkeypatch.setattr("app.services.goal_events.after_donation", _noop, raising=False)
    await _user(session, 555)
    await wallet_pay.apply_paid_order(session, _order(customData="anon=1;rub=300"))

    from app.db.models import Donation
    from sqlalchemy import select

    assert (await session.execute(select(Donation))).scalar_one().is_anonymous is True


async def test_unpaid_order_is_not_recorded(session, ton_ready):
    await _user(session, 555)
    assert await wallet_pay.apply_paid_order(session, _order(status="ACTIVE")) is False


async def test_order_without_user_is_not_recorded(session, ton_ready):
    """Покупателя нет в базе — записывать донат не на кого."""
    assert await wallet_pay.apply_paid_order(session, _order()) is False


async def test_order_without_external_id_is_not_recorded(session, ton_ready):
    """Без externalId нет ключа идемпотентности — повтор удвоил бы вклад."""
    await _user(session, 555)
    order = _order()
    del order["externalId"]
    assert await wallet_pay.apply_paid_order(session, order) is False


async def test_order_with_zero_amount_is_not_recorded(session, ton_ready):
    await _user(session, 555)
    assert (
        await wallet_pay.apply_paid_order(
            session, _order(customData="anon=0;rub=0", amount={"amount": "0"})
        )
        is False
    )


async def _noop(*args, **kwargs) -> None:
    return None

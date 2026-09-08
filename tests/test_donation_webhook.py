"""Вебхук ЮKassa: донат не должен выдавать Premium, а возврат — верить телу.

Это ровно то, что владелец просил проверить особо («защиту оплаты»).
"""
import pytest

from app.db.models import Donation, PremiumSubscription, User
from app.services import yookassa_payments as yk


async def _user(session, telegram_id: int = 555) -> User:
    user = User(telegram_id=telegram_id, username="donor")
    session.add(user)
    await session.flush()
    return user


def _payment(payment_id: str, amount: str, kind: str | None, telegram_id: int = 555) -> dict:
    metadata: dict[str, str] = {"telegram_id": str(telegram_id)}
    if kind:
        metadata["kind"] = kind
    return {
        "id": payment_id,
        "status": "succeeded",
        "amount": {"value": amount, "currency": "RUB"},
        "metadata": metadata,
    }


@pytest.fixture(autouse=True)
def _mute_notifications(monkeypatch):
    """Уведомления шлют HTTP — в тестах глушим, они не предмет проверки."""
    async def noop(*args, **kwargs):
        return True

    monkeypatch.setattr("app.services.telegram_send.send_message", noop)


@pytest.mark.asyncio
async def test_donation_does_not_grant_premium(session, monkeypatch):
    """Ключевой инвариант: за донат не выдаётся НИЧЕГО.

    Иначе дарение превращается в реализацию — с чеком и другой отчётностью,
    ровно то, чего решили избежать.
    """
    user = await _user(session)

    granted = []

    async def fake_activate(*args, **kwargs):
        granted.append(args)

    monkeypatch.setattr(yk, "activate_premium", fake_activate)

    assert await yk.apply_succeeded_payment(session, _payment("d1", "249.00", "donate")) is True
    assert granted == [], "донат не имеет права активировать Premium"
    assert await session.get(PremiumSubscription, user.id) is None
    donation = await session.scalar(
        Donation.__table__.select().where(Donation.payment_id == "d1")
    )
    assert donation is not None


@pytest.mark.asyncio
async def test_donation_webhook_is_idempotent(session):
    user = await _user(session)
    payment = _payment("d1", "500.00", "donate")
    assert await yk.apply_succeeded_payment(session, payment) is True
    # ЮKassa повторяет уведомление, пока не получит 200.
    assert await yk.apply_succeeded_payment(session, payment) is True

    from app.services.donations import user_total

    assert await user_total(session, user.id) == 500, "повтор не должен удваивать вклад"


@pytest.mark.asyncio
async def test_unknown_user_is_rejected(session):
    payment = _payment("d1", "100.00", "donate", telegram_id=999999)
    assert await yk.apply_succeeded_payment(session, payment) is False


@pytest.mark.asyncio
async def test_non_positive_amount_is_rejected(session):
    await _user(session)
    assert await yk.apply_succeeded_payment(session, _payment("d1", "0.00", "donate")) is False
    assert await yk.apply_succeeded_payment(session, _payment("d2", "-50.00", "donate")) is False


@pytest.mark.asyncio
async def test_broken_amount_does_not_crash_webhook(session):
    await _user(session)
    assert await yk.apply_succeeded_payment(session, _payment("d1", "не число", "donate")) is False


@pytest.mark.asyncio
async def test_refund_marks_donation(session):
    user = await _user(session)
    await yk.apply_succeeded_payment(session, _payment("d1", "700.00", "donate"))
    assert await yk.apply_refund(session, "d1") is True

    from app.services.donations import user_total

    assert await user_total(session, user.id) == 0


@pytest.mark.asyncio
async def test_donation_payment_rejects_bad_amount_before_calling_kassa(monkeypatch):
    """Сумма проверяется у самой границы с деньгами, а не только в хендлере."""
    called = []

    async def fake_post(payload):
        called.append(payload)
        return 200, {"confirmation": {"confirmation_url": "https://pay"}}

    monkeypatch.setattr(yk, "_post_payment", fake_post)

    assert await yk.create_donation_payment(1, "bot", 0) is None
    assert await yk.create_donation_payment(1, "bot", -100) is None
    assert await yk.create_donation_payment(1, "bot", 10**9) is None
    assert called == [], "в кассу не должно уйти ни одного такого платежа"

    assert await yk.create_donation_payment(1, "bot", 249) == "https://pay"
    assert called[0]["metadata"]["kind"] == "donate"
    assert called[0]["amount"]["value"] == "249.00"
    # Донат разовый — сохранять способ оплаты незачем и небезопасно.
    assert "save_payment_method" not in called[0]

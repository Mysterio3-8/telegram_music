from app.config import settings
from app.db.models import PremiumSubscription, User
from app.services.premium import is_premium_active
from app.services.yookassa_payments import apply_succeeded_payment, create_premium_payment


async def make_user(session) -> User:
    user = User(telegram_id=777)
    session.add(user)
    await session.commit()
    return user


def payment(payment_id="pay_1", status="succeeded", telegram_id="777") -> dict:
    return {"id": payment_id, "status": status, "metadata": {"telegram_id": telegram_id}}


async def test_apply_succeeded_payment_activates_premium(session):
    user = await make_user(session)

    ok = await apply_succeeded_payment(session, payment())

    assert ok is True
    await session.refresh(user)
    assert is_premium_active(user)
    subscription = await session.get(PremiumSubscription, user.id)
    assert subscription.type == "yookassa"
    assert subscription.payment_id == "pay_1"


async def test_apply_same_payment_twice_is_idempotent(session):
    user = await make_user(session)

    await apply_succeeded_payment(session, payment())
    await session.refresh(user)
    first_until = user.premium_until

    ok = await apply_succeeded_payment(session, payment())  # повторный webhook

    assert ok is True
    await session.refresh(user)
    assert user.premium_until == first_until  # срок не удвоился


async def test_apply_ignores_non_succeeded(session):
    user = await make_user(session)

    ok = await apply_succeeded_payment(session, payment(status="canceled"))

    assert ok is False
    await session.refresh(user)
    assert not is_premium_active(user)


async def test_apply_ignores_unknown_user(session):
    ok = await apply_succeeded_payment(session, payment(telegram_id="999999"))

    assert ok is False


async def test_create_payment_retries_without_save_method_on_forbidden(monkeypatch):
    """Регресс 2026-07-27: магазин не подключил рекуррент в ЮKassa — save_payment_method
    возвращал 403 forbidden и ВСЕ рублёвые платежи переставали создаваться. Теперь
    должен тихо повторить без сохранения способа оплаты и всё равно вернуть ссылку."""
    monkeypatch.setattr(settings, "premium_autorenew", True)
    calls = []

    async def fake_post(payload):
        calls.append(payload)
        if payload.get("save_payment_method"):
            return 403, {"code": "forbidden", "description": "This store can't make recurring payments"}
        return 200, {"confirmation": {"confirmation_url": "https://yookassa.ru/pay/xyz"}}

    monkeypatch.setattr("app.services.yookassa_payments._post_payment", fake_post)

    url = await create_premium_payment(777, "tgram_music_bot", 49, months=1)

    assert url == "https://yookassa.ru/pay/xyz"
    assert len(calls) == 2
    assert calls[0]["save_payment_method"] is True
    assert "save_payment_method" not in calls[1]


async def test_create_payment_succeeds_directly_when_recurring_allowed(monkeypatch):
    monkeypatch.setattr(settings, "premium_autorenew", True)
    calls = []

    async def fake_post(payload):
        calls.append(payload)
        return 200, {"confirmation": {"confirmation_url": "https://yookassa.ru/pay/ok"}}

    monkeypatch.setattr("app.services.yookassa_payments._post_payment", fake_post)

    url = await create_premium_payment(777, "tgram_music_bot", 49, months=1)

    assert url == "https://yookassa.ru/pay/ok"
    assert len(calls) == 1  # без лишнего повтора, когда рекуррент разрешён

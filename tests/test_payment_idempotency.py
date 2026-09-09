"""Идемпотентность денежных операций: повтор уведомления не должен ничего удваивать.

Находка аудита 2026-09-08. Прежняя защита сравнивала id платежа с ПОСЛЕДНИМ
применённым (`subscription.payment_id == payment.id`) и переставала работать
ровно тогда, когда человек платил второй раз: состояние затиралось вторым
платежом, и повторное уведомление по первому проходило защиту насквозь —
лишний месяц Premium и дубль в журнале выручки.

ЮKassa повторяет уведомление, пока не получит 200, поэтому сценарий не
теоретический.
"""
import pytest
from sqlalchemy import func, select

from app.db.models import Payment, PremiumSubscription, User
from app.services import yookassa_payments as yk
from app.services.revenue import record_payment


async def _user(session, telegram_id: int = 777) -> User:
    user = User(telegram_id=telegram_id, username="payer")
    session.add(user)
    await session.flush()
    return user


def _payment(payment_id: str, months: str, amount: str, telegram_id: int = 777) -> dict:
    return {
        "id": payment_id,
        "status": "succeeded",
        "amount": {"value": amount, "currency": "RUB"},
        "metadata": {"telegram_id": str(telegram_id), "months": months},
    }


async def _payments_count(session, charge_id: str) -> int:
    return await session.scalar(
        select(func.count()).select_from(Payment).where(Payment.charge_id == charge_id)
    )


@pytest.mark.asyncio
async def test_replay_after_second_payment_does_not_grant_twice(session):
    """A → B → повтор A. Раньше повтор A выдавал ещё месяц и дубль в выручке."""
    await _user(session)

    assert await yk.apply_succeeded_payment(session, _payment("pay-A", "1", "29.00"))
    assert await yk.apply_succeeded_payment(session, _payment("pay-B", "12", "278.00"))

    subscription = await session.get(PremiumSubscription, 1)
    end_after_b = subscription.end_date

    # Повторная доставка уведомления по первому платежу
    assert await yk.apply_succeeded_payment(session, _payment("pay-A", "1", "29.00"))

    await session.refresh(subscription)
    assert subscription.end_date == end_after_b, "повтор продлил подписку второй раз"
    assert await _payments_count(session, "pay-A") == 1, "дубль в журнале выручки"


@pytest.mark.asyncio
async def test_immediate_replay_is_ignored(session):
    """Простейший случай: то же уведомление приходит дважды подряд."""
    await _user(session)

    assert await yk.apply_succeeded_payment(session, _payment("pay-C", "1", "29.00"))
    subscription = await session.get(PremiumSubscription, 1)
    end_date = subscription.end_date

    assert await yk.apply_succeeded_payment(session, _payment("pay-C", "1", "29.00"))

    await session.refresh(subscription)
    assert subscription.end_date == end_date
    assert await _payments_count(session, "pay-C") == 1


@pytest.mark.asyncio
async def test_record_payment_dedups_by_charge_id(session):
    """Журнал выручки — не место для дублей: отчёт по нему принимает решения."""
    user = await _user(session)

    assert await record_payment(session, user.id, 29, "yookassa", "charge-1") is True
    assert await record_payment(session, user.id, 29, "yookassa", "charge-1") is False
    assert await _payments_count(session, "charge-1") == 1


@pytest.mark.asyncio
async def test_payments_without_charge_id_are_not_deduped(session):
    """У Stars и старых записей charge_id пуст — такие строки дублями не считаются,
    иначе второй платёж без id молча потерялся бы."""
    user = await _user(session)

    assert await record_payment(session, user.id, 100, "stars", None, amount_stars=100) is True
    assert await record_payment(session, user.id, 100, "stars", None, amount_stars=100) is True

    total = await session.scalar(
        select(func.count()).select_from(Payment).where(Payment.charge_id.is_(None))
    )
    assert total == 2

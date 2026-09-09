"""Статистика выручки (блок E): лог платежей + сводка день/неделя/месяц/всё время.

Рубли и Stars считаются РАЗДЕЛЬНО и складываться не должны: курс звезды
плавающий, Telegram удерживает свою долю, и число «рубли плюс звёзды» не
означало бы ничего. В отчёте это две строки, а не одна."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Payment

_RUB_SOURCES = ("yookassa", "card", "ton")
STARS_SOURCE = "stars"


async def payment_already_recorded(session: AsyncSession, charge_id: str) -> bool:
    """Этот платёж уже лежит в журнале? Ключ идемпотентности денежных операций.

    ⚠️ Спрашивать надо ЖУРНАЛ, а не текущее состояние подписки. Состояние
    перезаписывается следующим платежом, и защита, привязанная к нему, перестаёт
    работать ровно тогда, когда человек платит второй раз: повтор уведомления по
    первому платежу пройдёт её насквозь.
    """
    return (
        await session.scalar(select(Payment.id).where(Payment.charge_id == charge_id))
    ) is not None


async def record_payment(
    session: AsyncSession,
    user_id: int,
    amount_rub: int,
    source: str,
    charge_id: str | None = None,
    amount_stars: int = 0,
) -> bool:
    """Пишет платёж в журнал. False — такой charge_id уже учтён, ничего не сделано.

    ЮKassa повторяет уведомление, пока не получит 200, поэтому один и тот же
    платёж приходит по несколько раз. Без этой проверки повтор удваивал строку в
    журнале, и отчёт о выручке завышал сумму — а решения принимаются по нему.
    """
    if charge_id and await payment_already_recorded(session, charge_id):
        return False
    session.add(
        Payment(
            user_id=user_id,
            amount_rub=amount_rub,
            source=source,
            charge_id=charge_id,
            amount_stars=amount_stars,
        )
    )
    await session.commit()
    return True


@dataclass(frozen=True)
class RevenueStats:
    day: int
    week: int
    month: int
    total: int
    payments_total: int
    # Stars отдельными полями — см. модуль-docstring о том, почему не в сумме
    stars_total: int = 0
    stars_payments: int = 0


async def _sum_since(session: AsyncSession, since: datetime | None) -> int:
    stmt = select(func.coalesce(func.sum(Payment.amount_rub), 0)).where(
        Payment.source.in_(_RUB_SOURCES)
    )
    if since is not None:
        stmt = stmt.where(Payment.created_at >= since)
    return await session.scalar(stmt) or 0


async def collect_revenue(session: AsyncSession) -> RevenueStats:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    day = await _sum_since(session, now - timedelta(days=1))
    week = await _sum_since(session, now - timedelta(days=7))
    month = await _sum_since(session, now - timedelta(days=30))
    total = await _sum_since(session, None)
    count = await session.scalar(
        select(func.count()).select_from(Payment).where(Payment.source.in_(_RUB_SOURCES))
    ) or 0
    stars_total = await session.scalar(
        select(func.coalesce(func.sum(Payment.amount_stars), 0)).where(
            Payment.source == STARS_SOURCE
        )
    ) or 0
    stars_count = await session.scalar(
        select(func.count()).select_from(Payment).where(Payment.source == STARS_SOURCE)
    ) or 0
    return RevenueStats(
        day=day,
        week=week,
        month=month,
        total=total,
        payments_total=count,
        stars_total=stars_total,
        stars_payments=stars_count,
    )

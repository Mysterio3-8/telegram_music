"""Статистика выручки (блок E): лог платежей + сводка день/неделя/месяц/всё время.

Считаем рублёвые платежи (yookassa/card). Stars логируются отдельным source и в
рублёвую выручку не входят — их курс не фиксирован."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Payment

_RUB_SOURCES = ("yookassa", "card", "ton")


async def record_payment(
    session: AsyncSession, user_id: int, amount_rub: int, source: str, charge_id: str | None = None
) -> None:
    session.add(
        Payment(user_id=user_id, amount_rub=amount_rub, source=source, charge_id=charge_id)
    )
    await session.commit()


@dataclass(frozen=True)
class RevenueStats:
    day: int
    week: int
    month: int
    total: int
    payments_total: int


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
    return RevenueStats(day=day, week=week, month=month, total=total, payments_total=count)

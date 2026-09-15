"""Отчёт по воронке новичка: сколько людей прошли каждый шаг.

    python -m app.cli.funnel            # за 30 дней
    python -m app.cli.funnel --days 7

Шаг считается по людям, которые пришли (шаг «start») за окно, — иначе старые
пользователи, впервые открывшие Mini App, раздували бы нижние ступени.
"""
import argparse
import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.db.base import session_factory
from app.db.models import FunnelEvent
from app.services.funnel import STEPS


async def build_report(session, days: int) -> list[tuple[str, int]]:
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
    cohort = (
        select(FunnelEvent.user_id)
        .where(FunnelEvent.step == "start", FunnelEvent.created_at >= since)
        .scalar_subquery()
    )
    rows = await session.execute(
        select(FunnelEvent.step, func.count(func.distinct(FunnelEvent.user_id)))
        .where(FunnelEvent.user_id.in_(cohort))
        .group_by(FunnelEvent.step)
    )
    counts = dict(rows.all())
    return [(step, counts.get(step, 0)) for step in STEPS]


async def _main(days: int) -> None:
    async with session_factory() as session:
        report = await build_report(session, days)
    top = report[0][1] or 1
    print(f"Воронка новичков за {days} дн. (пришли: {report[0][1]})")
    for step, count in report:
        print(f"  {step:<14} {count:>5}  {count * 100 // top:>3}%")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=30)
    asyncio.run(_main(parser.parse_args().days))


if __name__ == "__main__":
    main()

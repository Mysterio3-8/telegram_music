"""Отбор запросов для прогрева каталога.

Прогрев стоит в ночном таймере, поэтому важна не только частота запроса, но и
окно: без него список «самых частых за всё время» не меняется, и со второй ночи
таймер перебирал бы одно и то же, находя «уже в базе».
"""
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.cli import warmup
from app.db.base import Base
from app.db.models import SearchQuery, User


@pytest_asyncio.fixture
async def factory(monkeypatch):
    """Подменяет общий session_factory на временную БД в памяти."""
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(warmup, "session_factory", maker)
    yield maker
    await engine.dispose()


async def _seed(maker, rows: list[tuple[str, int]]) -> None:
    """rows: (запрос, сколько дней назад он был)."""
    now = datetime.now(timezone.utc)
    async with maker() as session:
        user = User(telegram_id=1)
        session.add(user)
        await session.flush()
        for query, days_ago in rows:
            session.add(
                SearchQuery(
                    user_id=user.id,
                    query=query,
                    created_at=now - timedelta(days=days_ago),
                )
            )
        await session.commit()


@pytest.mark.asyncio
async def test_popular_sorted_by_frequency(factory):
    await _seed(factory, [("кизару", 0), ("кизару", 0), ("макан", 0)])

    assert await warmup.popular_queries(10) == ["кизару", "макан"]


@pytest.mark.asyncio
async def test_days_window_drops_old_queries(factory):
    # «мияги» искали чаще, но давно: ночному прогреву нужно то, что ищут сейчас
    await _seed(
        factory,
        [("мияги", 30), ("мияги", 30), ("мияги", 30), ("нурминский", 1)],
    )

    assert await warmup.popular_queries(10, days=7) == ["нурминский"]


@pytest.mark.asyncio
async def test_zero_days_means_all_time(factory):
    """Ручной прогон без --days ведёт себя как раньше — окна нет."""
    await _seed(factory, [("мияги", 30), ("нурминский", 1)])

    assert set(await warmup.popular_queries(10)) == {"мияги", "нурминский"}


@pytest.mark.asyncio
async def test_limit_caps_the_list(factory):
    await _seed(factory, [("а", 0), ("а", 0), ("б", 0)])

    assert await warmup.popular_queries(1) == ["а"]

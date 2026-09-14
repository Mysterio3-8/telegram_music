"""Сверка выдачи живого поиска с базой одним запросом (цикл 3, 14.09).

Раньше на каждого кандидата уходил отдельный SELECT: выдача в 30 треков —
30 запросов к SQLite на каждое нажатие поиска."""
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import models  # noqa: F401
from app.db.base import Base
from app.db.models import Track
from app.services.search import find_track_by_metadata, find_tracks_by_metadata_bulk
from app.services.search_index import build_search_index


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as seed:
        for artist, title, status in [
            ("Кизару", "Зеркало", "approved"),
            ("Kizaru", "Fake ID", "approved"),
            ("Kizaru", "Fake ID", "approved"),  # дубль: берём самый старый
            ("Hidden", "Pending", "pending"),
        ]:
            seed.add(
                Track(
                    title=title,
                    artist=artist,
                    duration=100,
                    search_index=build_search_index(artist, title),
                    moderation_status=status,
                )
            )
        await seed.commit()
    async with factory() as s:
        yield s
    await engine.dispose()


async def test_bulk_matches_single_lookup_in_order(session):
    pairs = [
        ("Kizaru", "Fake ID"),
        ("Nobody", "Nothing"),
        ("КИЗАРУ", "зеркало"),
        ("Hidden", "Pending"),
        ("", ""),
    ]
    bulk = await find_tracks_by_metadata_bulk(session, pairs)
    single = [await find_track_by_metadata(session, a, t) for a, t in pairs]
    assert [t.id if t else None for t in bulk] == [t.id if t else None for t in single]
    assert bulk[0].id == 2  # самый старый из дублей
    assert bulk[1] is None and bulk[3] is None and bulk[4] is None


async def test_bulk_is_one_query(session):
    statements = []

    def before(*_args, **_kwargs):
        statements.append(1)

    sync_engine = session.bind.sync_engine
    event.listen(sync_engine, "before_cursor_execute", before)
    try:
        await find_tracks_by_metadata_bulk(session, [(f"Artist {i}", f"Title {i}") for i in range(30)])
    finally:
        event.remove(sync_engine, "before_cursor_execute", before)
    assert len(statements) == 1


async def test_empty_pairs_skip_database(session):
    assert await find_tracks_by_metadata_bulk(session, []) == []

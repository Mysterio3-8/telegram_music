"""Дополнение минусов исполнителем и обложкой (19.09, скрины владельца)."""
from datetime import datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import models  # noqa: F401
from app.db.base import Base
from app.db.models import Instrumental
from app.services import minus_enrich
from app.services.minus_enrich import RETRY_AFTER, due_minuses, enrich_minus, needs_enrich
from app.services.track_lookup.ranking import Candidate


@pytest.fixture
async def factory():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


def _minus(**kwargs):
    base = dict(title="Дежавю", artist="Неизвестный", duration=180, tg_file_id="F")
    base.update(kwargs)
    return Instrumental(**base)


def test_needs_enrich_covers_both_holes():
    assert needs_enrich(_minus())  # нет ни обложки, ни исполнителя
    assert needs_enrich(_minus(artist="Kizaru"))  # обложки нет
    assert not needs_enrich(_minus(artist="Kizaru", cover_url="http://c/1.jpg"))


async def test_due_skips_full_and_recently_checked(factory):
    now = datetime(2026, 9, 20, 4, 0)
    async with factory() as session:
        session.add_all(
            [
                _minus(id=1),  # пустой — берём
                _minus(id=2, artist="Kizaru", cover_url="http://c/2.jpg"),  # полный
                _minus(id=3, enrich_checked_at=now - timedelta(days=1)),  # только смотрели
                _minus(id=4, enrich_checked_at=now - RETRY_AFTER - timedelta(days=1)),  # пора снова
            ]
        )
        await session.commit()
        due = await due_minuses(session, limit=10, now=now)
    assert [item.id for item in due] == [1, 4]


async def test_enrich_fills_holes_and_marks_attempt(factory, monkeypatch):
    found = Candidate(
        source="soundcloud", url="https://soundcloud.com/k/dejavu", title="Дежавю",
        duration=180, artist="Kizaru", cover_url="https://i1.sndcdn.com/a-t500x500.jpg",
    )
    monkeypatch.setattr(minus_enrich, "find_match", lambda _item: found)
    async with factory() as session:
        item = _minus(id=1)
        session.add(item)
        await session.commit()
        assert await enrich_minus(session, item) is True
        assert item.artist == "Kizaru" and item.cover_url == found.cover_url
        assert item.enrich_checked_at is not None


async def test_known_artist_is_not_overwritten(factory, monkeypatch):
    # У минуса исполнитель значит «чей бит» — догадкой источника его не перетираем
    found = Candidate(
        source="soundcloud", url="https://soundcloud.com/x/1", title="Дежавю",
        duration=180, artist="Чужой", cover_url="https://i1.sndcdn.com/b-t500x500.jpg",
    )
    monkeypatch.setattr(minus_enrich, "find_match", lambda _item: found)
    async with factory() as session:
        item = _minus(id=1, artist="Zvyaga")
        session.add(item)
        await session.commit()
        assert await enrich_minus(session, item) is True
        assert item.artist == "Zvyaga" and item.cover_url == found.cover_url


async def test_nothing_found_still_marks_attempt(factory, monkeypatch):
    # Иначе безнадёжный минус каждую ночь снова оказывался бы первым в очереди
    monkeypatch.setattr(minus_enrich, "find_match", lambda _item: None)
    now = datetime(2026, 9, 20, 4, 0)
    async with factory() as session:
        item = _minus(id=1)
        session.add(item)
        await session.commit()
        assert await enrich_minus(session, item, now=now) is False
        assert item.enrich_checked_at == now
        assert await due_minuses(session, limit=10, now=now) == []


def test_search_failure_is_silent(monkeypatch):
    def boom(*_args, **_kwargs):
        raise RuntimeError("SoundCloud лёг")

    monkeypatch.setattr("app.services.soundcloud_api.search_tracks", boom)
    assert minus_enrich.find_match(_minus()) is None

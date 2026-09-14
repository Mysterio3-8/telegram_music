"""Вес ответов API (цикл 2, 14.09): замер прода показал, что каждое открытие
Mini App тянуло /genres 70 КБ и онбординг — весь /artists 58 КБ ради 24 имён."""
from datetime import datetime, timedelta

import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.app import create_app
from app.api.deps import get_db
from app.api.security import create_access_token
from app.db import models  # noqa: F401
from app.db.base import Base
from app.db.models import Track, User


@pytest_asyncio.fixture
async def client():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as seed:
        seed.add(
            User(
                telegram_id=777,
                first_name="Paid",
                premium=True,
                premium_until=datetime.utcnow() + timedelta(days=30),
            )
        )
        seed.add_all(
            [Track(title=f"T{i}", artist=f"Artist {i % 40}", duration=100) for i in range(200)]
        )
        await seed.commit()

    async def override_get_db():
        async with factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()
    await engine.dispose()


def _auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(777)}"}


def test_artists_limit_trims_payload(client):
    full = client.get("/artists", headers=_auth()).json()
    short = client.get("/artists?limit=24", headers=_auth()).json()
    assert len(full) == 40
    assert len(short) == 24
    assert short == full[:24]  # тот же порядок: самые крупные первыми


def test_artists_limit_bounds(client):
    assert client.get("/artists?limit=0", headers=_auth()).status_code == 422
    assert client.get("/artists?limit=999999", headers=_auth()).status_code == 422


def test_playlists_counts_in_one_query(client):
    from sqlalchemy import event

    created = [client.post("/playlist", headers=_auth(), json={"title": f"P{i}"}).json()["id"] for i in range(6)]
    for pid in created[:3]:
        for track_id in (1, 2):
            assert client.post(f"/playlists/{pid}/tracks/{track_id}", headers=_auth()).status_code == 204

    app = client.app
    engine_holder = {}

    from app.api.deps import get_db

    original = app.dependency_overrides[get_db]

    async def counting_db():
        async for session in original():
            engine = session.bind
            statements = engine_holder.setdefault("n", [])

            def before(*_args, **_kwargs):
                statements.append(1)

            event.listen(engine.sync_engine, "before_cursor_execute", before)
            try:
                yield session
            finally:
                event.remove(engine.sync_engine, "before_cursor_execute", before)

    app.dependency_overrides[get_db] = counting_db
    body = client.get("/playlists", headers=_auth()).json()
    app.dependency_overrides[get_db] = original

    assert sorted(p["track_count"] for p in body) == [0, 0, 0, 2, 2, 2]
    # пользователь + плейлисты + один сгруппированный подсчёт; было 1 + N
    assert len(engine_holder["n"]) <= 3


def test_static_lists_are_cacheable(client):
    genres = client.get("/genres", headers=_auth())
    artists = client.get("/artists", headers=_auth())
    assert genres.headers["cache-control"] == "private, max-age=3600"
    assert artists.headers["cache-control"] == "private, max-age=300"

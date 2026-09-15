"""Веб-админка владельца (16.09): данные только локально, через SSH-туннель."""
from datetime import datetime, timedelta

import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.db import models  # noqa: F401
from app.db.base import Base
from app.db.models import Donation, Payment, Track, TrackEvent, User
from app.webadmin.server import check_token, create_app, get_session

NOW = datetime(2026, 9, 16, 12, 0, 0)


@pytest_asyncio.fixture
async def admin():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as seed:
        user = User(telegram_id=777, first_name="Илья", username="ilya",
                    created_at=NOW - timedelta(days=3), premium_until=NOW + timedelta(days=5))
        quiet = User(telegram_id=778, first_name="Гость", created_at=NOW - timedelta(days=40), bot_blocked=True)
        track = Track(title="Глубина", artist="Аметист", duration=180, tg_file_id="abc",
                      search_index="аметист глубина")
        seed.add_all([user, quiet, track])
        await seed.flush()
        seed.add_all([
            TrackEvent(user_id=user.id, track_id=track.id, event="listen", created_at=NOW - timedelta(hours=2)),
            Payment(user_id=user.id, amount_rub=49, source="yookassa", created_at=NOW - timedelta(days=1)),
            Donation(user_id=user.id, amount_rub=149, payment_id="d1", created_at=NOW - timedelta(days=2)),
        ])
        await seed.commit()

    async def override():
        async with factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_session] = override
    yield TestClient(app), app
    app.dependency_overrides.clear()
    await engine.dispose()


def test_overview_gives_numbers_and_daily_series(admin):
    client, _ = admin
    data = client.get("/api/overview?days=30").json()
    assert data["report"]["users_total"] == 2
    assert data["report"]["listens"] == 1
    assert data["catalog"]["tracks_total"] == 1
    assert data["revenue"]["total"] == 49
    assert data["donations"]["rub"] == 149
    assert len(data["series"]) == 31  # ряд по дням для графика, включая сегодня
    assert {"day", "listens", "users"} == set(data["series"][0])


def test_users_search_by_name_and_telegram_id(admin):
    client, _ = admin
    assert client.get("/api/users").json()["total"] == 2
    by_name = client.get("/api/users?q=илья").json()
    assert by_name["total"] == 1 and by_name["items"][0]["premium_active"] is True
    by_id = client.get("/api/users?q=778").json()
    assert by_id["total"] == 1 and by_id["items"][0]["blocked"] is True


def test_tracks_search_handles_cyrillic_case(admin):
    """SQLite lower() не понижает кириллицу — грабля проекта, ловим тестом."""
    client, _ = admin
    for query in ("аметист", "Аметист", "глубина"):
        found = client.get(f"/api/tracks?q={query}").json()
        assert found["total"] == 1, query
        assert found["items"][0]["playable"] is True


def test_money_lists_payments_and_donations(admin):
    client, _ = admin
    data = client.get("/api/money").json()
    assert data["payments"][0]["rub"] == 49
    assert data["donations"][0]["rub"] == 149 and data["donations"][0]["refunded"] is False


def test_token_guards_when_set(admin, monkeypatch):
    client, app = admin
    app.dependency_overrides.pop(check_token, None)
    # Заголовки HTTP — только ASCII, поэтому токен латиницей
    monkeypatch.setattr(settings, "webadmin_token", "s3cret-token")
    assert client.get("/api/users").status_code == 401
    assert client.get("/api/users", headers={"X-Admin-Token": "s3cret-token"}).status_code == 200

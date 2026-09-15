"""Пробный период Mini App — 7 дней, один раз (решение владельца 15.09).

Mini App включает его сам при первом открытии по флагу trial_available из
/premium/status, поэтому флаг и срок обязаны приходить с сервера.
"""
from datetime import datetime, timedelta

import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.app import create_app
from app.api.deps import get_db
from app.api.security import create_access_token
from app.db import models  # noqa: F401
from app.db.base import Base
from app.db.models import User
from app.services.gamification import TRIAL_DAYS


@pytest_asyncio.fixture
async def client():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as seed:
        seed.add(User(telegram_id=556, first_name="Free"))
        seed.add(User(telegram_id=557, first_name="Used", trial_used=True))
        await seed.commit()

    async def override_get_db():
        async with factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()
    await engine.dispose()


def _auth(telegram_id: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(telegram_id)}"}


def test_trial_is_seven_days():
    assert TRIAL_DAYS == 7


def test_status_tells_miniapp_to_start_trial(client):
    body = client.get("/premium/status", headers=_auth(556)).json()
    assert body["active"] is False
    assert body["trial_available"] is True
    assert body["trial_days"] == 7


def test_trial_opens_app_for_seven_days_once(client):
    started = client.post("/premium/trial", headers=_auth(556))
    assert started.status_code == 200
    body = started.json()
    assert body["active"] is True
    assert body["trial_available"] is False
    until = datetime.fromisoformat(body["until"].replace("Z", "+00:00")).replace(tzinfo=None)
    left = until - datetime.utcnow()
    assert timedelta(days=6, hours=23) < left <= timedelta(days=7)

    assert client.post("/premium/trial", headers=_auth(556)).status_code == 409
    assert client.get("/library/ids", headers=_auth(556)).status_code == 200


def test_used_trial_is_not_offered_again(client):
    body = client.get("/premium/status", headers=_auth(557)).json()
    assert body["trial_available"] is False
    assert client.post("/premium/trial", headers=_auth(557)).status_code == 409

from datetime import datetime, timedelta, timezone

import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.app import create_app
from app.api.deps import get_db
from app.api.security import create_access_token
from app.db import models  # noqa: F401
from app.db.base import Base
from app.db.models import Contest, User

USER_TELEGRAM_ID = 555


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@pytest_asyncio.fixture
async def api():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as seed:
        seed.add(User(telegram_id=USER_TELEGRAM_ID, first_name="Ivan"))
        seed.add(
            Contest(
                title="Розыгрыш Premium",
                description="Условия конкурса",
                banner_text="Выиграй Premium",
                prize_days=30,
                ends_at=_utcnow() + timedelta(days=14),
            )
        )
        await seed.commit()

    async def override_get_db():
        async with factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    yield client, create_access_token(USER_TELEGRAM_ID), factory
    app.dependency_overrides.clear()
    await engine.dispose()


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_active_contest_is_listed_with_user_state(api):
    client, token, _ = api

    response = client.get("/contests", headers=_auth(token))

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["title"] == "Розыгрыш Premium"
    assert body[0]["joined"] is False
    assert body[0]["can_join"] is True
    assert body[0]["participants"] == 0


def test_join_registers_participation_once(api):
    client, token, _ = api

    first = client.post("/contests/1/join", headers=_auth(token))
    assert first.status_code == 200
    assert first.json()["joined"] is True
    assert first.json()["contest"]["participants"] == 1

    # Повторное нажатие не создаёт второго участия и не ломает ответ
    second = client.post("/contests/1/join", headers=_auth(token))
    assert second.status_code == 200
    assert second.json()["contest"]["participants"] == 1

    listed = client.get("/contests", headers=_auth(token)).json()[0]
    assert listed["joined"] is True
    assert listed["can_join"] is False


def test_join_rejected_when_referrals_missing(api):
    client, token, factory = api

    async def _require_referrals():
        async with factory() as session:
            contest = await session.get(Contest, 1)
            contest.required_referrals = 3
            await session.commit()

    import asyncio

    asyncio.get_event_loop().run_until_complete(_require_referrals())

    response = client.post("/contests/1/join", headers=_auth(token))

    assert response.status_code == 409
    assert "услови" in response.json()["detail"].lower()


def test_unauthorized_without_token(api):
    client, _, _ = api
    assert client.get("/contests").status_code == 401

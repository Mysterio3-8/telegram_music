"""Воронка новичка (15.09): шаги пишутся один раз и не ломают сценарий."""
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.app import create_app
from app.api.deps import get_db
from app.api.security import create_access_token
from app.cli.funnel import build_report
from app.db import models  # noqa: F401
from app.db.base import Base
from app.db.models import FunnelEvent, User
from app.services import funnel


@pytest.fixture(autouse=True)
def _fresh_seen():
    funnel.forget_seen_steps()
    yield
    funnel.forget_seen_steps()


async def _user(session, telegram_id=900) -> User:
    user = User(telegram_id=telegram_id)
    session.add(user)
    await session.commit()
    return user


async def test_step_is_recorded_once(session):
    user = await _user(session)
    for _ in range(3):
        await funnel.record_step(session, user.id, "gate_shown")
    funnel.forget_seen_steps()  # и после рестарта процесса — не дублируется
    await funnel.record_step(session, user.id, "gate_shown")
    count = await session.scalar(select(func.count()).select_from(FunnelEvent))
    assert count == 1


async def test_unknown_step_is_programming_error(session):
    user = await _user(session)
    with pytest.raises(ValueError):
        await funnel.record_step(session, user.id, "typo_step")


async def test_write_failure_does_not_break_flow(session, monkeypatch):
    user = await _user(session)

    async def boom(*_args, **_kwargs):
        raise RuntimeError("db is locked")

    monkeypatch.setattr(session, "scalar", boom)
    await funnel.record_step(session, user.id, "start")  # не бросает


async def test_report_counts_people_of_the_cohort(session):
    first = await _user(session, 901)
    second = await _user(session, 902)
    old = await _user(session, 903)  # пришёл до окна: шага start нет
    for user in (first, second):
        await funnel.record_step(session, user.id, "start")
        await funnel.record_step(session, user.id, "gate_passed")
    await funnel.record_step(session, first.id, "cabinet_shown")
    await funnel.record_step(session, old.id, "miniapp_login")
    report = dict(await build_report(session, days=30))
    assert report["start"] == 2
    assert report["gate_passed"] == 2
    assert report["cabinet_shown"] == 1
    assert report["miniapp_login"] == 0
    assert list(report) == list(funnel.STEPS)


@pytest_asyncio.fixture
async def api():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as seed:
        seed.add(User(telegram_id=556, first_name="Free"))
        await seed.commit()

    async def override_get_db():
        async with factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app), factory
    app.dependency_overrides.clear()
    await engine.dispose()


async def test_miniapp_login_and_paywall_are_recorded(api, monkeypatch):
    client, factory = api
    from app.api.routers import auth

    monkeypatch.setattr(auth, "validate_init_data", lambda _raw: {"id": 556, "first_name": "Free"})
    assert client.post("/login", json={"init_data": "signed"}).status_code == 200
    token = {"Authorization": f"Bearer {create_access_token(556)}"}
    for _ in range(3):
        assert client.get("/library/ids", headers=token).status_code == 402

    async with factory() as session:
        steps = (await session.scalars(select(FunnelEvent.step))).all()
    assert sorted(steps) == ["miniapp_login", "paywall_hit"]

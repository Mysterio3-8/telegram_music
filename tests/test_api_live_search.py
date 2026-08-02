"""API живого поиска: выдача, ref, полки. Сеть подменяем — проверяем контракт."""
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.app import create_app
from app.api.deps import get_db
from app.api.security import create_access_token
from app.db import models  # noqa: F401
from app.db.base import Base
from app.db.models import Track, User
from app.services.track_lookup.ranking import Candidate

FOUND = [
    Candidate(
        source="soundcloud",
        url="https://soundcloud.test/fake-id",
        title="Kizaru - Fake ID",
        duration=175,
        artist="Kizaru",
        cover_url="http://cover/1",
    ),
    Candidate(
        source="youtube",
        url="https://youtube.test/watch?v=1",
        title="Kizaru - Nirvana",
        duration=190,
        artist=None,
    ),
]


@pytest_asyncio.fixture
async def api(monkeypatch):
    async def fake_search(query, limit=None):
        return FOUND

    # Сети в тестах быть не должно. Роутер импортирует функцию на уровне модуля,
    # полки — лениво внутри функций, поэтому подменяем обе точки.
    monkeypatch.setattr("app.api.routers.live_search.search_with_cache", fake_search)
    monkeypatch.setattr("app.services.search_cache.search_with_cache", fake_search)

    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as seed:
        seed.add(User(telegram_id=555, first_name="Ivan"))
        await seed.commit()

    async def override_get_db():
        async with factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app), create_access_token(555), factory

    app.dependency_overrides.clear()
    await engine.dispose()


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_live_search_returns_candidates_with_refs(api):
    client, token, _ = api
    response = client.get("/search/live", params={"q": "кизару"}, headers=auth(token))
    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["artist"] for item in items] == ["Kizaru", "Kizaru"]
    assert all(item["ref"] for item in items)
    # ничего не найдено в базе → играть через поток
    assert all(item["track_id"] is None for item in items)


@pytest.mark.asyncio
async def test_known_track_comes_back_with_track_id(api):
    client, token, factory = api
    async with factory() as session:
        from app.services.search_index import build_search_index

        session.add(
            Track(
                title="Fake ID",
                artist="Kizaru",
                duration=175,
                search_index=build_search_index("Kizaru", "Fake ID"),
            )
        )
        await session.commit()

    items = client.get("/search/live", params={"q": "кизару"}, headers=auth(token)).json()["items"]
    assert items[0]["track_id"] is not None  # играем мгновенно по file_id, не потоком


def test_live_search_requires_auth(api):
    client, _, _ = api
    assert client.get("/search/live", params={"q": "x"}).status_code == 401


def test_stream_rejects_broken_ref(api):
    client, _, _ = api
    assert client.get("/stream/garbage").status_code == 403


def test_shelves_are_listed(api):
    client, token, _ = api
    shelves = client.get("/shelves", headers=auth(token)).json()
    assert {"slug", "name"} <= set(shelves[0])
    assert any(shelf["slug"] == "drive" for shelf in shelves)


def test_unknown_shelf_is_404(api):
    client, token, _ = api
    assert client.get("/shelves/nope", headers=auth(token)).status_code == 404

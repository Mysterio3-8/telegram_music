import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.app import create_app
from app.api.deps import get_db
from app.api.security import create_access_token
from app.db import models  # noqa: F401
from app.db.base import Base
from app.db.models import Instrumental, Track, User


@pytest_asyncio.fixture
async def api():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as seed:
        seed.add(User(telegram_id=555, first_name="Ivan"))
        seed.add_all(
            [
                Track(title="Believer", artist="Imagine Dragons", duration=204),
                Track(title="Thunder", artist="Imagine Dragons", duration=187),
                Instrumental(title="Night Minus", artist="Zvyaga", duration=120),
            ]
        )
        await seed.commit()

    async def override_get_db():
        async with factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    token = create_access_token(555)
    yield client, token

    app.dependency_overrides.clear()
    await engine.dispose()


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_health_is_public(api):
    client, _ = api
    assert client.get("/health").json() == {"status": "ok"}


def test_tracks_requires_auth(api):
    client, _ = api
    assert client.get("/tracks").status_code in (401, 403)  # нет Bearer


def test_tracks_rejects_bad_token(api):
    client, _ = api
    response = client.get("/tracks", headers=auth_header("garbage"))
    assert response.status_code == 401


def test_list_tracks(api):
    client, token = api
    response = client.get("/tracks", headers=auth_header(token))
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert {t["title"] for t in body["items"]} == {"Believer", "Thunder"}
    assert "storage_path" not in body["items"][0]  # внутренние поля не утекают


def test_track_by_id_returns_fresh_audio_url(api):
    client, token = api
    response = client.get("/track/1", headers=auth_header(token))
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == 1
    assert "/tracks/1/audio?exp=" in body["audio_url"]


def test_track_by_negative_id_returns_instrumental(api):
    """Отрицательный id — минус: фронт освежает протухшие ссылки единым эндпоинтом."""
    client, token = api
    response = client.get("/track/-1", headers=auth_header(token))
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == -1
    assert body["title"] == "Night Minus"
    assert "/instrumentals/1/audio?exp=" in body["audio_url"]


def test_search_filters(api):
    client, token = api
    response = client.get("/search", params={"q": "believer"}, headers=auth_header(token))
    assert response.status_code == 200
    assert response.json()["total"] == 1


def test_get_track_404(api):
    client, token = api
    assert client.get("/track/999", headers=auth_header(token)).status_code == 404


def test_login_rejects_bad_init_data(api):
    client, _ = api
    response = client.post("/login", json={"init_data": "user=%7B%7D&hash=deadbeef"})
    assert response.status_code == 401


def test_premium_status_defaults_free(api):
    client, token = api
    response = client.get("/premium/status", headers=auth_header(token))
    assert response.status_code == 200
    assert response.json()["active"] is False

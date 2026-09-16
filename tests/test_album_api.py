"""Альбомы в Mini App (16.09): поиск, треки альбома, «добавить весь альбом»."""
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.app import create_app
from app.api.deps import get_db
from app.api.security import create_access_token
from app.db import models  # noqa: F401
from app.db.base import Base
from app.db.models import User
from app.services.albums import AlbumCandidate
from app.services.track_lookup.ranking import Candidate


@pytest_asyncio.fixture
async def client():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as seed:
        from datetime import datetime, timedelta

        seed.add(User(telegram_id=901, premium=True, premium_until=datetime.utcnow() + timedelta(days=5)))
        seed.add(User(telegram_id=902))
        await seed.commit()

    async def override():
        async with factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_db] = override
    yield TestClient(app)
    app.dependency_overrides.clear()
    await engine.dispose()


PREMIUM = {"Authorization": f"Bearer {create_access_token(901)}"}
FREE = {"Authorization": f"Bearer {create_access_token(902)}"}
TRACKS = [
    Candidate(source="soundcloud", url=f"https://soundcloud.com/s/{i}", title=f"Трек {i}", duration=180, artist="Скриптонит")
    for i in range(1, 4)
]


def test_album_routes_are_behind_paywall(client):
    assert client.get("/search/live/albums?q=2004", headers=FREE).status_code == 402
    assert client.get("/albums/live/5", headers=FREE).status_code == 402
    assert client.post("/albums/live/5/library", headers=FREE).status_code == 402


def test_search_albums_returns_cards(client, monkeypatch):
    album = AlbumCandidate(1, "2004", "Скриптонит", "u", 24, "c.jpg", "album", True, 10)
    monkeypatch.setattr("app.services.albums.search_albums", lambda q, limit=5: [album])
    data = client.get("/search/live/albums?q=скриптонит 2004", headers=PREMIUM).json()
    assert data == [{"id": 1, "title": "2004", "artist": "Скриптонит", "track_count": 24, "cover_url": "c.jpg", "official": True}]


def test_album_tracks_have_stream_refs(client, monkeypatch):
    monkeypatch.setattr("app.services.albums.album_tracks", lambda album_id: TRACKS)
    items = client.get("/albums/live/970298674", headers=PREMIUM).json()["items"]
    assert [i["title"] for i in items] == ["Трек 1", "Трек 2", "Трек 3"]
    assert all(i["ref"] for i in items)


def test_album_not_found_and_bad_ids(client, monkeypatch):
    monkeypatch.setattr("app.services.albums.album_tracks", lambda album_id: [])
    assert client.get("/albums/live/5", headers=PREMIUM).status_code == 404
    assert client.get("/albums/live/0", headers=PREMIUM).status_code == 404
    assert client.get(f"/albums/live/{10**15}", headers=PREMIUM).status_code == 404


def test_add_album_queues_quietly_once(client, monkeypatch):
    monkeypatch.setattr("app.services.albums.album_tracks", lambda album_id: TRACKS)
    queued, locked = [], set()

    def acquire(tid):
        if tid in locked:
            return False
        locked.add(tid)
        return True

    monkeypatch.setattr("app.services.albums.acquire_album_lock", acquire)
    monkeypatch.setattr("app.tasks.queue_client.enqueue", lambda name, **kw: queued.append((name, kw)))
    first = client.post("/albums/live/77/library", headers=PREMIUM)
    assert first.status_code == 200 and first.json() == {"queued": True, "count": 3, "minutes": 1}
    name, kwargs = queued[0]
    assert name == "album.fetch_all" and kwargs["chat_id"] is None and len(kwargs["tracks"]) == 3
    assert client.post("/albums/live/77/library", headers=PREMIUM).status_code == 409
    assert len(queued) == 1

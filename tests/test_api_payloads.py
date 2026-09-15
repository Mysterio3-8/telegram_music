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


async def test_upload_refused_when_all_slots_busy(client):
    """Файл до 50 МБ держится в памяти: одновременных загрузок не больше UPLOAD_SLOTS."""
    from app.api.routers import me

    for _ in range(me.UPLOAD_SLOTS):
        await me._upload_slots.acquire()
    try:
        response = client.post(
            "/upload",
            headers=_auth(),
            data={"title": "T", "artist": "A"},
            files={"file": ("t.mp3", b"ID3" + b"\x00" * 100, "audio/mpeg")},
        )
    finally:
        for _ in range(me.UPLOAD_SLOTS):
            me._upload_slots.release()
    assert response.status_code == 503
    assert response.headers["retry-after"] == "60"


def _wav_bytes(seconds: int = 2) -> bytes:
    import io
    import wave

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(b"\x00\x00" * 8000 * seconds)
    return buffer.getvalue()


class _MemoryStorage:
    def __init__(self) -> None:
        self.saved: dict[str, int] = {}

    def save(self, key: str, data: bytes) -> str:
        self.saved[key] = len(data)
        return f"memory://{key}"


def test_upload_streams_to_temp_file_and_offloads_heavy_work(client, monkeypatch, tmp_path):
    """Цикл 8: отпечаток (fpcalc) и длительность — в пуле потоков, а не в event
    loop; временный файл убирается; байты доходят до хранилища целиком."""
    import asyncio
    import tempfile

    from app.api.routers import me
    from app.services import fingerprint

    spool = tmp_path / "spool"
    spool.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(spool))
    storage = _MemoryStorage()
    monkeypatch.setattr(me, "get_storage", lambda: storage)
    seen = {}

    def fake_fingerprint(path: str) -> str:
        seen["path_exists"] = __import__("os").path.exists(path)
        try:
            asyncio.get_running_loop()
            seen["in_event_loop"] = True
        except RuntimeError:
            seen["in_event_loop"] = False
        return "FP-UPLOAD"

    monkeypatch.setattr(fingerprint, "compute_fingerprint", fake_fingerprint)
    data = _wav_bytes()
    response = client.post(
        "/upload",
        headers=_auth(),
        data={"title": "Своя", "artist": "Автор"},
        files={"file": ("mine.wav", data, "audio/wav")},
    )
    assert response.status_code == 201, response.text
    assert response.json()["duration"] == 2
    assert seen == {"path_exists": True, "in_event_loop": False}
    assert list(storage.saved.values()) == [len(data)]
    assert list(spool.iterdir()) == []


def test_upload_over_limit_is_400_and_leaves_no_temp(client, monkeypatch, tmp_path):
    import tempfile

    from app.api.routers import me
    from app.config import settings

    spool = tmp_path / "spool"
    spool.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(spool))
    monkeypatch.setattr(settings, "max_file_size_mb", 0)
    monkeypatch.setattr(me, "get_storage", lambda: _MemoryStorage())
    response = client.post(
        "/upload",
        headers=_auth(),
        data={"title": "T", "artist": "A"},
        files={"file": ("big.wav", _wav_bytes(), "audio/wav")},
    )
    assert response.status_code == 400
    assert list(spool.iterdir()) == []


def test_static_lists_are_cacheable(client):
    genres = client.get("/genres", headers=_auth())
    artists = client.get("/artists", headers=_auth())
    assert genres.headers["cache-control"] == "private, max-age=3600"
    assert artists.headers["cache-control"] == "private, max-age=300"

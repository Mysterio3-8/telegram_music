"""Стрим аудио Mini App с диска кусками (цикл 2, 14.09).

Раньше каждый Range-запрос читал весь трек в память, а десять одновременных
«play» по треку без кэша качали его из Telegram десять раз."""
import asyncio
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.app import create_app
from app.api.routers import audio as audio_router
from app.api.security import build_audio_url
from app.config import settings
from app.db import models  # noqa: F401
from app.db.base import Base
from app.db.models import Track

DATA = bytes(range(256)) * 4000  # ~1 МБ, больше одного куска стрима


@pytest_asyncio.fixture
async def env(tmp_path, monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as seed:
        seed.add(Track(title="Cached", artist="A", duration=10, tg_file_id="cached-id"))
        seed.add(Track(title="Cold", artist="B", duration=10, tg_file_id="cold-id"))
        await seed.commit()

    monkeypatch.setattr(audio_router, "session_factory", factory)
    monkeypatch.setattr(settings, "audio_cache_dir", str(tmp_path))
    monkeypatch.setattr(settings, "audio_cache_max_mb", 50)
    (tmp_path / "tracks_1").write_bytes(DATA)

    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    await engine.dispose()


async def test_full_file_streams_from_disk(env, monkeypatch):
    def no_memory_load(*_args, **_kwargs):
        raise AssertionError("стрим не должен читать трек целиком в память")

    monkeypatch.setattr(audio_router, "cache_get", no_memory_load)
    response = await env.get(build_audio_url(1))
    assert response.status_code == 200
    assert response.content == DATA
    assert response.headers["content-length"] == str(len(DATA))


async def test_range_is_served_from_file(env):
    response = await env.get(build_audio_url(1), headers={"Range": "bytes=1000-1999"})
    assert response.status_code == 206
    assert response.content == DATA[1000:2000]
    assert response.headers["content-range"] == f"bytes 1000-1999/{len(DATA)}"


async def test_suffix_range_from_file(env):
    response = await env.get(build_audio_url(1), headers={"Range": "bytes=-100"})
    assert response.status_code == 206
    assert response.content == DATA[-100:]


@pytest.mark.parametrize("header", ["bytes=abc", "bytes=10-5", "bytes=0-1,5-6", f"bytes={len(DATA)}-"])
async def test_bad_range_is_416(env, header):
    response = await env.get(build_audio_url(1), headers={"Range": header})
    assert response.status_code == 416


async def test_cold_track_downloads_once_for_concurrent_plays(env, monkeypatch):
    calls = []

    async def fake_download(self, file_id, destination=None, **_kwargs):
        calls.append(file_id)
        await asyncio.sleep(0.05)  # окно, в которое влетают остальные «play»
        Path(destination).write_bytes(DATA)

    monkeypatch.setattr(audio_router.BotApi, "download", fake_download)
    url = build_audio_url(2)
    responses = await asyncio.gather(*[env.get(url) for _ in range(10)])
    assert [r.status_code for r in responses] == [200] * 10
    assert all(r.content == DATA for r in responses)
    assert calls == ["cold-id"]
    assert not audio_router._download_locks  # замки не копятся


async def test_failed_download_is_404_and_leaves_no_tmp(env, monkeypatch, tmp_path):
    async def broken(self, file_id, destination=None, **_kwargs):
        Path(destination).write_bytes(b"half")
        raise RuntimeError("telegram down")

    async def no_heal(_track_id):
        return None

    monkeypatch.setattr(audio_router.BotApi, "download", broken)
    monkeypatch.setattr(audio_router, "_heal_dead_file_id", no_heal)
    response = await env.get(build_audio_url(2))
    assert response.status_code == 404
    assert not list(tmp_path.glob("*.tmp"))


async def test_bad_signature_still_403(env):
    response = await env.get("/tracks/1/audio?exp=9999999999&sig=forged")
    assert response.status_code == 403


async def test_accel_redirect_hands_file_to_nginx(env, monkeypatch):
    """С префиксом API не шлёт байты: nginx отдаёт файл кэша сам (цикл 6)."""
    monkeypatch.setattr(settings, "audio_accel_redirect_prefix", "/_audio_cache/")
    response = await env.get(build_audio_url(1), headers={"Range": "bytes=0-99"})
    assert response.status_code == 200  # Range разбирает nginx, не API
    assert response.headers["x-accel-redirect"] == "/_audio_cache/tracks_1"
    assert response.headers["content-type"].startswith("audio/mpeg")
    assert response.content == b""


async def test_accel_redirect_still_checks_signature(env, monkeypatch):
    monkeypatch.setattr(settings, "audio_accel_redirect_prefix", "/_audio_cache/")
    response = await env.get("/tracks/1/audio?exp=9999999999&sig=forged")
    assert response.status_code == 403
    assert "x-accel-redirect" not in response.headers


async def test_accel_redirect_only_for_cache_directory(env, monkeypatch, tmp_path):
    from app.api.routers.audio import _accel_redirect

    monkeypatch.setattr(settings, "audio_accel_redirect_prefix", "/_audio_cache/")
    outside = tmp_path.parent / "elsewhere.mp3"
    outside.write_bytes(b"x")
    try:
        assert _accel_redirect(outside, "audio/mpeg") is None
    finally:
        outside.unlink()

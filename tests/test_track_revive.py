"""Трек с мёртвым file_id оживает прямо в запросе (владелец 22.09).

Раньше API отдавал 404, а Mini App писал «Восстанавливаем эти треки — попробуйте
через минуту». Владелец: «такого вообще не должно быть, и надписи этой не должно
быть вообще… пусть загрузится и включится». Значит, проверяем ровно это: байты
доезжают в том же запросе, а мёртвый идентификатор гасится.
"""
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

pytestmark = pytest.mark.asyncio

DATA = b"ID3" + bytes(range(256)) * 100


@pytest_asyncio.fixture
async def env(tmp_path, monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as seed:
        seed.add(
            Track(
                title="Dead",
                artist="A",
                duration=10,
                tg_file_id="dead-id",
                source_url="https://soundcloud.com/a/dead",
            )
        )
        await seed.commit()

    monkeypatch.setattr(audio_router, "session_factory", factory)
    monkeypatch.setattr(settings, "audio_cache_dir", str(tmp_path))
    monkeypatch.setattr(settings, "audio_cache_max_mb", 50)
    monkeypatch.setattr(settings, "audio_accel_redirect_prefix", "")

    async def dead_download(self, file_id, destination=None, **_kwargs):
        raise RuntimeError("wrong file identifier")

    monkeypatch.setattr(audio_router.BotApi, "download", dead_download)

    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, factory
    await engine.dispose()


async def test_dead_file_id_is_downloaded_from_source_in_the_same_request(env, monkeypatch):
    client, factory = env
    queued: list[int] = []
    monkeypatch.setattr(audio_router, "_enqueue_repair", lambda track_id: queued.append(track_id) or True)

    async def fast(_url):
        return DATA

    monkeypatch.setattr(audio_router, "_fast_bytes", fast)

    response = await client.get(build_audio_url(1))
    assert response.status_code == 200
    assert response.content == DATA
    # Минт всё равно заказан: кэш на диске вытесняется, а file_id — нет
    assert queued == [1]
    async with factory() as session:
        track = await session.get(Track, 1)
        assert track.tg_file_id is None  # мёртвый идентификатор погашен
        assert track.meta_synced is False


async def test_no_source_and_no_worker_is_honest_404(env, monkeypatch):
    client, _factory = env

    async def nothing(_url):
        return None

    monkeypatch.setattr(audio_router, "_fast_bytes", nothing)
    monkeypatch.setattr(audio_router, "_enqueue_repair", lambda track_id: False)

    response = await client.get(build_audio_url(1))
    assert response.status_code == 404


async def test_worker_mint_is_awaited(env, monkeypatch):
    """Быстрый путь не сработал — ждём воркер и отдаём то, что он заминтил."""
    client, factory = env

    async def nothing(_url):
        return None

    monkeypatch.setattr(audio_router, "_fast_bytes", nothing)
    monkeypatch.setattr(audio_router, "_REVIVE_POLL_SECONDS", 0.01)
    monkeypatch.setattr(audio_router, "_REVIVE_WAIT_SECONDS", 1.0)

    def enqueue(track_id: int) -> bool:
        return True

    monkeypatch.setattr(audio_router, "_enqueue_repair", enqueue)

    async def minted(storage_key, tg_file_id):
        from pathlib import Path

        path = Path(settings.audio_cache_dir) / storage_key.replace("/", "_")
        path.write_bytes(DATA)
        return path

    monkeypatch.setattr(audio_router, "_download_from_telegram", minted)

    # Воркер «заминтил» трек сразу после постановки задачи
    async with factory() as session:
        track = await session.get(Track, 1)
        track.tg_file_id = "fresh-id"
        await session.commit()

    response = await client.get(build_audio_url(1))
    assert response.status_code == 200
    assert response.content == DATA


async def test_worker_failure_answers_at_once(env, monkeypatch):
    """Прогон 25.09: воркер сдавался за 1.6 сек, а API ждал ещё 25 — плеер на 0:00."""
    import time

    from app.services import track_repair

    client, _factory = env
    failed = set()

    async def nothing(_url):
        return None

    def enqueue(track_id):
        failed.add(track_id)  # воркер тут же не справился
        return True

    monkeypatch.setattr(audio_router, "_fast_bytes", nothing)
    monkeypatch.setattr(audio_router, "_REVIVE_POLL_SECONDS", 0.01)
    monkeypatch.setattr(audio_router, "_REVIVE_WAIT_SECONDS", 5.0)
    monkeypatch.setattr(audio_router, "_enqueue_repair", enqueue)
    monkeypatch.setattr(track_repair, "recently_failed", lambda track_id: track_id in failed)

    started = time.monotonic()
    response = await client.get(build_audio_url(1))
    assert response.status_code == 404
    assert time.monotonic() - started < 2


async def test_recent_failure_skips_worker(env, monkeypatch):
    from app.services import track_repair

    client, _factory = env
    queued = []

    async def nothing(_url):
        return None

    monkeypatch.setattr(audio_router, "_fast_bytes", nothing)
    monkeypatch.setattr(audio_router, "_enqueue_repair", lambda track_id: queued.append(track_id) or True)
    monkeypatch.setattr(track_repair, "recently_failed", lambda track_id: True)
    response = await client.get(build_audio_url(1))
    assert response.status_code == 404
    assert queued == []  # недавно не вышло — воркер впустую не гоняем

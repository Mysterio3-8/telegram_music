"""Регрессия на находки стресс-теста 13.09: каждая проверка воспроизводила баг."""
import asyncio
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import ratelimit
from app.api.app import create_app
from app.api.deps import get_db
from app.api.routers import audio as audio_router
from app.api.routers import subscription as subscription_router
from app.api.security import create_access_token
from app.db import models  # noqa: F401
from app.db.base import Base
from app.db.models import (
    Artist,
    Lyrics,
    Playlist,
    PlaylistTrack,
    RequiredChannel,
    Track,
    User,
    UserArtist,
    UserLibrary,
)
from app.services.gamification import start_trial
from app.services.library import add_to_library


@pytest_asyncio.fixture
async def env():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as seed:
        seed.add_all(
            [
                User(telegram_id=555, first_name="Free"),
                User(
                    telegram_id=777,
                    first_name="Paid",
                    premium=True,
                    premium_until=datetime.utcnow() + timedelta(days=30),
                ),
                Track(title="Believer", artist="Imagine Dragons", duration=204),
                Artist(name="Imagine Dragons", normalized_name="imagine dragons"),
                RequiredChannel(channel="@chan", label="Канал"),
            ]
        )
        await seed.commit()

    async def override_get_db():
        async with factory() as session:
            yield session

    ratelimit.RateLimitMiddleware  # noqa: B018 — лимитер свой на каждый create_app
    subscription_router._recent_clicks.clear()
    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app), factory
    app.dependency_overrides.clear()
    await engine.dispose()


def _auth(telegram_id: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(telegram_id)}"}


async def _count(factory, stmt) -> int:
    async with factory() as session:
        return await session.scalar(stmt)


def test_free_user_cannot_overwrite_shared_lyrics(env):
    client, _ = env
    response = client.post("/tracks/1/lyrics", headers=_auth(555), json={"text": "VANDAL"})
    assert response.status_code == 402  # с 14.09 весь API Mini App закрыт пэйволом


def test_lyrics_length_is_capped(env):
    client, _ = env
    response = client.post("/tracks/1/lyrics", headers=_auth(777), json={"text": "a" * 20_001})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_premium_user_still_saves_lyrics(env):
    client, factory = env
    response = client.post("/tracks/1/lyrics", headers=_auth(777), json={"text": "Куплет"})
    assert response.status_code == 201
    assert await _count(factory, select(func.count()).select_from(Lyrics)) == 1


def test_playlist_title_length_is_capped(env):
    client, _ = env
    response = client.post("/playlist", headers=_auth(777), json={"title": "x" * 129})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_playlist_rejects_unknown_track_without_orphan(env):
    client, factory = env
    created = client.post("/playlist", headers=_auth(777), json={"title": "QA"}).json()
    response = client.post(f"/playlists/{created['id']}/tracks/999999", headers=_auth(777))
    assert response.status_code == 404
    assert await _count(factory, select(func.count()).select_from(PlaylistTrack)) == 0


@pytest.mark.asyncio
async def test_follow_unknown_artist_is_404_without_orphan(env):
    client, factory = env
    assert client.post("/artists/999999/follow", headers=_auth(777)).status_code == 404
    assert await _count(factory, select(func.count()).select_from(UserArtist)) == 0
    assert client.post("/artists/1/follow", headers=_auth(777)).status_code == 204


def test_huge_id_is_404_not_500(env):
    client, _ = env
    response = client.get("/track/99999999999999999999", headers=_auth(777))
    assert response.status_code == 404


def test_upload_with_blank_title_is_400(env):
    client, _ = env
    response = client.post(
        "/upload",
        headers=_auth(777),
        data={"title": " ", "artist": " "},
        files={"file": ("x.mp3", b"\x00" * 1000, "audio/mpeg")},
    )
    assert response.status_code == 400


def test_upload_of_garbage_mp3_is_400_not_500(env):
    client, _ = env
    response = client.post(
        "/upload",
        headers=_auth(777),
        data={"title": "Трек", "artist": "Автор"},
        files={"file": ("x.mp3", b"\x00" * 1000, "audio/mpeg")},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_channel_click_counts_once_per_user(env):
    client, factory = env
    for _ in range(5):
        assert client.post("/subscription/click/1", headers=_auth(555)).status_code == 204
    client.post("/subscription/click/1", headers=_auth(777))
    async with factory() as session:
        channel = await session.get(RequiredChannel, 1)
    assert channel.click_count == 2


def test_rate_limit_answer_has_retry_after(env):
    client, _ = env
    last = None
    for _ in range(ratelimit.GENERAL_LIMIT + 1):
        last = client.get("/health", headers={**_auth(777), "X-Real-IP": "10.9.9.9"})
    assert last.status_code == 429
    assert last.headers.get("Retry-After") == "60"


def test_suffix_range_returns_tail():
    data = bytes(range(256)) * 4
    response = audio_router._range_response(data, "bytes=-100", "audio/mpeg")
    assert response.status_code == 206
    assert response.body == data[-100:]
    assert response.headers["Content-Range"] == f"bytes {len(data) - 100}-{len(data) - 1}/{len(data)}"


@pytest.mark.parametrize("header", ["bytes=-0", "bytes=-", "bytes=abc"])
def test_bad_suffix_range_is_416(header):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as caught:
        audio_router._range_response(b"abc", header, "audio/mpeg")
    assert caught.value.status_code == 416


@pytest.mark.asyncio
async def test_concurrent_library_add_is_not_500(tmp_path):
    # Файловая база: у in-memory SQLite каждое соединение — своя пустая база,
    # и честной гонки двух соединений на ней не получить.
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'race.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as seed:
        seed.add_all([User(telegram_id=1), Track(title="T", artist="A", duration=1)])
        await seed.commit()

    async def add():
        async with factory() as session:
            return await add_to_library(session, 1, 1)

    try:
        results = await asyncio.gather(*[add() for _ in range(6)], return_exceptions=True)
        assert not [r for r in results if isinstance(r, Exception)], results
        assert results.count(True) == 1, results
        assert await _count(factory, select(func.count()).select_from(UserLibrary)) == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_trial_is_claimed_once_under_concurrency(env):
    _, factory = env

    async def claim():
        async with factory() as session:
            user = await session.get(User, 1)
            return await start_trial(session, user)

    results = await asyncio.gather(*[claim() for _ in range(8)])
    assert results.count(True) == 1


@pytest.mark.asyncio
async def test_payment_link_does_not_burn_discount(env, monkeypatch):
    client, factory = env
    async with factory() as session:
        user = await session.get(User, 1)
        user.premium_discount_pct = 50
        await session.commit()

    captured = {}

    async def fake_create(telegram_id, bot_username, price, months=1, discount_pct=0):
        captured.update(price=price, discount_pct=discount_pct)
        return "https://pay.example/confirm"

    from app.api.routers import payments

    monkeypatch.setattr(payments, "is_yookassa_configured", lambda: True)
    monkeypatch.setattr(payments, "create_premium_payment", fake_create)
    response = client.post("/premium/pay", headers=_auth(555), json={"months": 1})
    assert response.status_code == 200
    assert captured["discount_pct"] == 50
    async with factory() as session:
        assert (await session.get(User, 1)).premium_discount_pct == 50


@pytest.mark.asyncio
async def test_successful_payment_consumes_discount(env, monkeypatch):
    _, factory = env
    from app.services import yookassa_payments

    async with factory() as session:
        user = await session.get(User, 1)
        user.premium_discount_pct = 50
        await session.commit()
        payment = {
            "id": "pay-1",
            "status": "succeeded",
            "amount": {"value": "15.00"},
            "metadata": {"telegram_id": "555", "months": "1", "discount_pct": "50"},
        }
        assert await yookassa_payments.apply_succeeded_payment(session, payment)
    async with factory() as session:
        assert (await session.get(User, 1)).premium_discount_pct == 0


@pytest.mark.asyncio
async def test_transfer_is_capped_and_locked(env, monkeypatch):
    client, _ = env
    from app.config import settings
    from app.services.playlist_transfer import service
    from app.tasks import transfer as transfer_task

    queued = []
    locks = {"held": False}

    def acquire(_tid):
        if locks["held"]:
            return False
        locks["held"] = True
        return True

    monkeypatch.setattr(settings, "celery_broker_url", "memory://")
    monkeypatch.setattr(service, "acquire_transfer_lock", acquire)
    monkeypatch.setattr(transfer_task.transfer_playlist_task, "delay", lambda items, tid: queued.append(len(items)))

    text = "\n".join(f"Artist{i} — Title{i}" for i in range(1500))
    first = client.post("/transfer", headers=_auth(777), json={"source": text})
    assert first.status_code == 200
    assert first.json()["queued"] == service.TRANSFER_MAX_ITEMS
    assert first.json()["skipped"] == 500
    assert queued == [service.TRANSFER_MAX_ITEMS]

    second = client.post("/transfer", headers=_auth(777), json={"source": "A — B"})
    assert second.status_code == 409


def test_transfer_does_not_use_search_queue():
    from app.tasks.celery_app import celery_app

    assert celery_app.conf.task_routes["transfer.playlist"]["queue"] != "youtube_user"


@pytest.mark.asyncio
async def test_transfer_finds_cyrillic_track_by_search_index(env):
    _, factory = env
    from app.services.playlist_transfer.parsers import TransferItem
    from app.services.playlist_transfer.service import find_in_catalog
    from app.services.search_index import build_search_index

    async with factory() as session:
        track = Track(
            title="Назови",
            artist="МАКАН",
            duration=180,
            search_index=build_search_index("МАКАН", "Назови"),
        )
        session.add(track)
        await session.commit()
        found = await find_in_catalog(session, TransferItem("макан", "назови"))
    assert found is not None and found.title == "Назови"

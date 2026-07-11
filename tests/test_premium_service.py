from datetime import timedelta

from app.config import settings
from app.db.models import PremiumSubscription, Track, Upload, User
from app.services.premium import (
    _utcnow,
    activate_premium,
    can_create_playlist,
    can_upload,
    is_premium_active,
    refresh_premium_status,
)
from app.services.playlists import create_playlist


async def make_user(session, premium=False, premium_until=None) -> User:
    user = User(telegram_id=1, premium=premium, premium_until=premium_until)
    session.add(user)
    await session.commit()
    return user


def test_is_premium_active_states():
    now = _utcnow()
    assert is_premium_active(User(telegram_id=1, premium=True, premium_until=now + timedelta(days=1)))
    assert not is_premium_active(User(telegram_id=1, premium=True, premium_until=now - timedelta(days=1)))
    assert not is_premium_active(User(telegram_id=1, premium=True, premium_until=None))
    assert not is_premium_active(User(telegram_id=1, premium=False, premium_until=now + timedelta(days=1)))


async def test_activate_premium_sets_flag_and_subscription(session):
    user = await make_user(session)

    updated = await activate_premium(session, user.id, "stars", "charge_1")

    assert updated.premium is True
    assert is_premium_active(updated)
    assert updated.premium_until > _utcnow() + timedelta(days=settings.premium_duration_days - 1)
    subscription = await session.get(PremiumSubscription, user.id)
    assert subscription.status == "active"
    assert subscription.type == "stars"
    assert subscription.payment_id == "charge_1"


async def test_activate_premium_extends_active_subscription(session):
    user = await make_user(session, premium=True, premium_until=_utcnow() + timedelta(days=10))

    updated = await activate_premium(session, user.id, "card", "charge_2")

    expected_min = _utcnow() + timedelta(days=10 + settings.premium_duration_days - 1)
    assert updated.premium_until > expected_min


async def test_refresh_premium_status_downgrades_expired(session):
    user = await make_user(session, premium=True, premium_until=_utcnow() - timedelta(days=1))

    await refresh_premium_status(session, user)

    assert user.premium is False


async def test_refresh_keeps_active_premium(session):
    user = await make_user(session, premium=True, premium_until=_utcnow() + timedelta(days=5))

    await refresh_premium_status(session, user)

    assert user.premium is True


async def test_can_create_playlist_respects_free_limit(session):
    user = await make_user(session)
    for i in range(settings.free_playlist_limit):
        await create_playlist(session, user.id, f"P{i}")

    assert await can_create_playlist(session, user) is False


async def test_premium_user_bypasses_playlist_limit(session):
    user = await make_user(session, premium=True, premium_until=_utcnow() + timedelta(days=5))
    for i in range(settings.free_playlist_limit + 3):
        await create_playlist(session, user.id, f"P{i}")

    assert await can_create_playlist(session, user) is True


async def test_can_upload_respects_free_limit(session):
    user = await make_user(session)
    for i in range(settings.free_upload_limit):
        track = Track(title=f"T{i}", artist="A", duration=100)
        session.add(track)
        await session.flush()
        session.add(Upload(user_id=user.id, track_id=track.id))
    await session.commit()

    assert await can_upload(session, user) is False


async def test_premium_user_bypasses_upload_limit(session):
    user = await make_user(session, premium=True, premium_until=_utcnow() + timedelta(days=5))

    assert await can_upload(session, user) is True

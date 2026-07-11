from datetime import timedelta

from app.db.models import Track, User
from app.services.stats import _utcnow, collect_stats, record_event


async def make_user(session, telegram_id: int = 1) -> User:
    user = User(telegram_id=telegram_id, last_login=_utcnow())
    session.add(user)
    await session.commit()
    return user


async def make_track(session, title: str = "Song", artist: str = "Artist") -> Track:
    track = Track(title=title, artist=artist, duration=200)
    session.add(track)
    await session.commit()
    return track


async def test_stats_count_users_tracks_and_events(session):
    user = await make_user(session)
    track = await make_track(session)
    await record_event(session, user.id, track.id, "listen")
    await record_event(session, user.id, track.id, "listen")
    await record_event(session, user.id, track.id, "download")

    stats = await collect_stats(session)

    assert stats.users_total == 1
    assert stats.users_new_day == 1
    assert stats.users_active_day == 1
    assert stats.tracks_total == 1
    assert stats.listens_total == 2
    assert stats.downloads_total == 1


async def test_stats_top_tracks_ordered_by_events(session):
    user = await make_user(session)
    hit = await make_track(session, "Hit")
    other = await make_track(session, "Other")
    for _ in range(3):
        await record_event(session, user.id, hit.id, "listen")
    await record_event(session, user.id, other.id, "listen")

    stats = await collect_stats(session)

    assert [(t.id, n) for t, n in stats.top_tracks] == [(hit.id, 3), (other.id, 1)]


async def test_stats_old_users_not_counted_as_new_or_active(session):
    user = await make_user(session)
    user.created_at = _utcnow() - timedelta(days=30)
    user.last_login = _utcnow() - timedelta(days=30)
    await session.commit()

    stats = await collect_stats(session)

    assert stats.users_total == 1
    assert stats.users_new_day == 0
    assert stats.users_new_week == 0
    assert stats.users_active_day == 0
    assert stats.users_active_week == 0

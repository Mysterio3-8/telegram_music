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


async def test_stats_count_users_and_tracks(session):
    user = await make_user(session)
    track = await make_track(session)
    # события всё ещё пишутся (нужны для достижений), но в статистике больше не показываются
    await record_event(session, user.id, track.id, "listen")
    await record_event(session, user.id, track.id, "download")

    stats = await collect_stats(session)

    assert stats.users_total == 1
    assert stats.users_new_day == 1
    assert stats.users_active_all_time == 1
    assert stats.tracks_total == 1


async def test_active_all_time_counts_old_users(session):
    user = await make_user(session)
    user.created_at = _utcnow() - timedelta(days=30)
    user.last_login = _utcnow() - timedelta(days=30)
    await session.commit()

    stats = await collect_stats(session)

    assert stats.users_total == 1
    assert stats.users_new_day == 0
    assert stats.users_active_all_time == 1  # заходил хоть раз


async def test_active_all_time_ignores_never_logged_in(session):
    user = User(telegram_id=2, last_login=None)
    session.add(user)
    await session.commit()

    stats = await collect_stats(session)

    assert stats.users_total == 1
    assert stats.users_active_all_time == 0

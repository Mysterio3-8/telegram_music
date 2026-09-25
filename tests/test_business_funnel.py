"""Воронка «пришёл → нашёл трек → вернулся → заплатил» (владелец 21.09, 25.09)."""
from datetime import datetime, timedelta

from app.db.models import FunnelEvent, Payment, SearchQuery, Track, TrackEvent, User
from app.services.business_funnel import build_funnel


async def _person(session, tid, *, days_ago=2):
    created = datetime.utcnow() - timedelta(days=days_ago)
    user = User(telegram_id=tid, first_name="T", created_at=created)
    session.add(user)
    await session.flush()
    session.add(FunnelEvent(user_id=user.id, step="start", created_at=created))
    return user


async def test_counts_people_along_the_path(session):
    track = Track(title="T", artist="A", duration=100)
    session.add(track)
    a = await _person(session, 1)  # пришёл, искал, получил трек, вернулся, заплатил
    b = await _person(session, 2)  # пришёл, искал и ушёл
    await _person(session, 3)  # пришёл и ничего
    await session.flush()
    now = datetime.utcnow()
    session.add_all([
        SearchQuery(user_id=a.id, query="kizaru", created_at=a.created_at),
        SearchQuery(user_id=b.id, query="macan", created_at=b.created_at),
        TrackEvent(user_id=a.id, track_id=track.id, event="listen", created_at=now),
        Payment(user_id=a.id, amount_rub=49, source="yookassa"),
    ])
    await session.commit()

    steps = {s.key: s.people for s in await build_funnel(session, days=30)}
    assert steps["start"] == 3
    assert steps["searched"] == 2
    assert steps["got_track"] == 1
    assert steps["returned"] == 1
    assert steps["paid"] == 1


async def test_old_users_do_not_inflate_the_cohort(session):
    """Давний пользователь, пришедший вне окна, в воронку не попадает."""
    await _person(session, 10, days_ago=90)
    steps = {s.key: s.people for s in await build_funnel(session, days=30)}
    assert steps["start"] == 0 and steps["paid"] == 0


async def test_same_day_activity_is_not_a_return(session):
    track = Track(title="T", artist="A", duration=100)
    session.add(track)
    user = await _person(session, 20)
    session.add(TrackEvent(user_id=user.id, track_id=track.id, event="listen", created_at=user.created_at))
    await session.commit()
    steps = {s.key: s.people for s in await build_funnel(session, days=30)}
    assert steps["got_track"] == 1 and steps["returned"] == 0

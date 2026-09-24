

async def test_listen_seconds_update_does_not_double_count(session):
    """Секунды дописываются к событию, а не создают новое: иначе одно
    прослушивание считалось бы дважды."""
    from sqlalchemy import func, select

    from app.db.models import Track, TrackEvent, User
    from app.services.stats import record_event, update_listen_seconds

    user = User(telegram_id=9001, first_name="T")
    track = Track(title="T", artist="A", duration=200)
    session.add_all([user, track])
    await session.flush()

    await record_event(session, user.id, track.id, "listen", source="miniapp")
    await update_listen_seconds(session, user.id, track.id, 45)

    count = await session.scalar(select(func.count()).select_from(TrackEvent))
    row = await session.scalar(select(TrackEvent))
    assert count == 1
    assert row.seconds == 45


async def test_listen_seconds_never_shrink(session):
    """Повторный отчёт о том же треке не укорачивает засчитанное."""
    from sqlalchemy import select

    from app.db.models import Track, TrackEvent, User
    from app.services.stats import record_event, update_listen_seconds

    user = User(telegram_id=9002, first_name="T")
    track = Track(title="T", artist="A", duration=200)
    session.add_all([user, track])
    await session.flush()

    await record_event(session, user.id, track.id, "listen", source="miniapp")
    await update_listen_seconds(session, user.id, track.id, 120)
    await update_listen_seconds(session, user.id, track.id, 10)

    row = await session.scalar(select(TrackEvent))
    assert row.seconds == 120

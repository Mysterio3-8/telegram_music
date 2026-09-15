"""Журнал аналитики (15.09): белые списки, компактные свойства, источник у прослушиваний."""
import json

import pytest
from sqlalchemy import select

from app.db.models import AnalyticsEvent, Track, TrackEvent, User
from app.services import analytics
from app.services.stats import record_event


async def _user_and_track(session) -> tuple[User, Track]:
    user = User(telegram_id=4242)
    track = Track(title="Song", artist="Artist", duration=180)
    session.add_all([user, track])
    await session.commit()
    return user, track


async def test_event_is_stored_with_props(session):
    user, track = await _user_and_track(session)
    await analytics.track_event(
        session, "search", source="bot", user_id=user.id, props={"results": 0, "q": "кизару"}
    )
    event = (await session.scalars(select(AnalyticsEvent))).one()
    assert (event.name, event.source, event.user_id) == ("search", "bot", user.id)
    assert json.loads(event.props) == {"results": 0, "q": "кизару"}


def test_unknown_names_and_sources_are_bugs():
    with pytest.raises(ValueError):
        analytics.build_event("listne", source="bot")
    with pytest.raises(ValueError):
        analytics.build_event("listen", source="telegram")


def test_oversized_props_become_a_marker_not_broken_json():
    encoded = analytics.encode_props({"blob": "x" * 5000})
    assert json.loads(encoded) == {"truncated": True}
    assert analytics.encode_props(None) is None


async def test_listen_records_source_once_per_dedup_window(session):
    user, track = await _user_and_track(session)
    await record_event(session, user.id, track.id, "listen", source="miniapp")
    await record_event(session, user.id, track.id, "listen", source="miniapp")  # дедуп 30 сек
    await record_event(session, user.id, track.id, "download", source="bot")

    listens = (await session.scalars(select(TrackEvent).where(TrackEvent.event == "listen"))).all()
    events = (await session.scalars(select(AnalyticsEvent).order_by(AnalyticsEvent.id))).all()
    assert len(listens) == 1
    assert [(e.name, e.source, e.track_id) for e in events] == [
        ("listen", "miniapp", track.id),
        ("download", "bot", track.id),
    ]


async def test_write_failure_is_swallowed(session, monkeypatch):
    async def boom():
        raise RuntimeError("database is locked")

    monkeypatch.setattr(session, "commit", boom)
    await analytics.track_event(session, "share_click", source="miniapp")  # не бросает

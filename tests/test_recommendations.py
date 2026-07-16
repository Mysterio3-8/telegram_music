from datetime import timedelta

from app.db.models import Track, TrackEvent, User
from app.services.premium import _utcnow
from app.services.recommendations import build_mix, detect_language


def test_detect_language():
    assert detect_language("Тишина") == "russian"
    assert detect_language("Deep Purple Sky") == "foreign"
    assert detect_language("Клип feat. Band") == "russian"


async def _track(session, title, artist="A", mood=None, created=None) -> Track:
    track = Track(title=title, artist=artist, duration=200, mood=mood)
    if created is not None:
        track.created_at = created
    session.add(track)
    await session.commit()
    return track


async def test_mix_filters_by_language(session):
    await _track(session, "Тишина")
    await _track(session, "Ocean")
    mix = await build_mix(session, language="foreign")
    assert [t.title for t in mix] == ["Ocean"]


async def test_mix_mood_soft_filter(session):
    await _track(session, "A", mood="happy")
    await _track(session, "B", mood=None)
    happy = await build_mix(session, mood="happy")
    assert [t.title for t in happy] == ["A"]

    # если нет треков с настроением — фильтр игнорируется (микс не пустеет)
    calm = await build_mix(session, mood="calm")
    assert len(calm) == 2


async def test_mix_recognizability_new_orders_by_date(session):
    old = await _track(session, "Old", created=_utcnow() - timedelta(days=10))
    new = await _track(session, "New", created=_utcnow())
    mix = await build_mix(session, recognizability="new")
    assert mix[0].title == "New"
    assert old in mix


async def test_mix_recognizability_known_orders_by_plays(session):
    hit = await _track(session, "Hit")
    quiet = await _track(session, "Quiet")
    user = User(telegram_id=1)
    session.add(user)
    await session.commit()
    for _ in range(3):
        session.add(TrackEvent(user_id=user.id, track_id=hit.id, event="listen"))
    await session.commit()

    known = await build_mix(session, recognizability="known")
    assert known[0].title == "Hit"

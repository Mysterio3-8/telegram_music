from datetime import timedelta

from app.db.models import Artist, Instrumental, MixHistory, Track, TrackEvent, User
from app.services.premium import _utcnow
from app.services.recommendations import (
    _spread_artists,
    build_mix,
    detect_language,
    instrumental_mix,
)
from app.services.title_quality import is_probably_junk


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


def test_spread_artists_no_run_of_three():
    class T:
        def __init__(self, i, artist):
            self.id = i
            self.artist = artist

    tracks = [T(i, "X") for i in range(5)] + [T(i, "Y") for i in range(5, 8)]
    spread = _spread_artists(tracks)
    # нигде не идёт 3 подряд одного артиста, пока есть чем разбавить
    runs = 1
    for a, b in zip(spread, spread[1:]):
        runs = runs + 1 if a.artist == b.artist else 1
        assert runs <= 2 or all(t.artist == "X" for t in spread[spread.index(b):])


async def test_junk_titles_excluded_from_mix(session):
    await _track(session, "Хороший трек")
    await _track(session, "Новый клип (премьера)")
    mix = await build_mix(session)
    titles = [t.title for t in mix]
    assert "Хороший трек" in titles
    assert "Новый клип (премьера)" not in titles


def test_is_probably_junk():
    assert is_probably_junk("Артист — Трек (Official Video)")
    assert is_probably_junk("Премьера клипа")
    assert not is_probably_junk("Big Baby Tape — Gimme the Loot (Remix)")
    assert not is_probably_junk("Элджей - Розовое вино")


async def test_mix_prefers_taste_artists(session):
    artist = Artist(name="Kizaru", normalized_name="kizaru")
    session.add(artist)
    await session.commit()
    fav = await _track(session, "Fav track", artist="Kizaru")
    fav.artist_id = artist.id
    for i in range(6):
        await _track(session, f"Other {i}", artist=f"Band{i}")
    user = User(telegram_id=10)
    session.add(user)
    await session.commit()
    session.add(TrackEvent(user_id=user.id, track_id=fav.id, event="listen"))
    await session.commit()

    mix = await build_mix(session, user_id=user.id, limit=3)
    assert fav.id in [t.id for t in mix]


async def test_mix_excludes_recently_shown(session):
    for i in range(4):
        await _track(session, f"T{i}", created=_utcnow() - timedelta(minutes=i))
    user = User(telegram_id=11)
    session.add(user)
    await session.commit()

    first = await build_mix(session, user_id=user.id, limit=2)
    assert len(first) == 2
    second = await build_mix(session, user_id=user.id, limit=2)
    assert set(t.id for t in first).isdisjoint(t.id for t in second)
    saved = await session.scalars(select_mix_history(user.id))
    assert len(list(saved)) == 4


def select_mix_history(user_id):
    from sqlalchemy import select

    return select(MixHistory.track_id).where(MixHistory.user_id == user_id)


async def test_instrumental_mix_returns_instrumentals(session):
    session.add(Instrumental(title="Минус 1", artist="A", duration=120))
    session.add(Instrumental(title="Минус 2", artist="B", duration=130))
    await session.commit()

    mix = await instrumental_mix(session)
    assert sorted(i.title for i in mix) == ["Минус 1", "Минус 2"]

"""Альбомы и обложки из карточки трека в источнике (владелец 22.09).

Замер прода 24.09: альбом был у 281 трека из 8547 — экран «Альбомы» пустовал.
"""
from sqlalchemy import select

from app.db.models import Track
from app.services import track_meta_enrich

SC = "https://soundcloud.com/kizaru_hf/fake-id"


async def _track(session, **fields) -> Track:
    track = Track(title="Fake ID", artist="kizaru", duration=200, source_url=SC, **fields)
    session.add(track)
    await session.commit()
    return track


def _card(album="BORN TO TRAP", artwork="https://i1.sndcdn.com/artworks-x-large.jpg"):
    return {"kind": "track", "publisher_metadata": {"album_title": album}, "artwork_url": artwork}


async def test_album_and_hi_res_cover_are_filled(session):
    track = await _track(session)
    report = await track_meta_enrich.enrich_tracks(session, fetch=lambda _url: _card())
    await session.refresh(track)
    assert track.album == "BORN TO TRAP"
    # «-large» — это 100×100: в карточку идёт t500x500 с того же CDN
    assert track.cover_url.endswith("-t500x500.jpg")
    assert report.albums == 1 and report.covers == 1


async def test_admin_edits_are_not_overwritten(session):
    track = await _track(session, album="Мой альбом", cover_url="https://my/cover.jpg")
    await track_meta_enrich.enrich_tracks(session, fetch=lambda _url: _card())
    await session.refresh(track)
    assert track.album == "Мой альбом"
    assert track.cover_url == "https://my/cover.jpg"


async def test_track_is_not_asked_twice_in_a_row(session):
    """Без отметки ночной проход вечно перебирал бы одни и те же синглы."""
    await _track(session)
    calls: list[str] = []

    def nothing(url):
        calls.append(url)
        return {"kind": "track"}

    await track_meta_enrich.enrich_tracks(session, fetch=nothing)
    await track_meta_enrich.enrich_tracks(session, fetch=nothing)
    assert len(calls) == 1


async def test_dead_source_still_marks_the_track(session):
    track = await _track(session)

    def boom(_url):
        raise RuntimeError("SoundCloud down")

    report = await track_meta_enrich.enrich_tracks(session, fetch=boom)
    await session.refresh(track)
    assert report.failed == 1
    assert track.meta_checked_at is not None


async def test_non_soundcloud_tracks_are_skipped(session):
    session.add(Track(title="Y", artist="A", duration=100, source_url="https://youtube.com/watch?v=1"))
    await session.commit()
    assert await track_meta_enrich.due_tracks(session, 10) == []
    assert (await session.scalars(select(Track))).all()

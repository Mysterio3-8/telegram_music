from app.db.models import Instrumental, Track
from app.services.search import search_instrumentals, search_tracks


async def add_tracks(session, titles: list[str]) -> list[Track]:
    tracks = [Track(title=title, artist="Imagine Dragons", duration=200) for title in titles]
    session.add_all(tracks)
    await session.commit()
    return tracks


async def test_search_tracks_matches_title_and_artist(session):
    await add_tracks(session, ["Believer", "Thunder"])
    session.add(Track(title="Other", artist="Nobody", duration=100))
    await session.commit()

    by_title, total_title = await search_tracks(session, "believer", page=1)
    by_artist, total_artist = await search_tracks(session, "imagine", page=1)

    assert total_title == 1
    assert by_title[0].title == "Believer"
    assert total_artist == 2
    assert len(by_artist) == 2


async def test_search_tracks_pagination_and_total(session):
    await add_tracks(session, [f"Song {i:02d}" for i in range(12)])

    page1, total = await search_tracks(session, "Song", page=1)
    page3, _ = await search_tracks(session, "Song", page=3)

    assert total == 12
    assert len(page1) == 5
    assert len(page3) == 2


async def test_search_tracks_no_results(session):
    tracks, total = await search_tracks(session, "nothing", page=1)

    assert tracks == []
    assert total == 0


async def test_search_instrumentals(session):
    session.add(Instrumental(title="Believer (Минус)", artist="Imagine Dragons", duration=210))
    await session.commit()

    results, total = await search_instrumentals(session, "believer", page=1)

    assert total == 1
    assert results[0].title == "Believer (Минус)"

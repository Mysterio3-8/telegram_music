from app.db.models import Track, User
from app.services.library import (
    add_to_library,
    get_library_page,
    get_random_track,
    remove_from_library,
    search_library,
)
from app.services.users import count_library_tracks


async def make_user(session) -> User:
    user = User(telegram_id=1)
    session.add(user)
    await session.commit()
    return user


async def make_track(session, title: str, artist: str = "Artist") -> Track:
    track = Track(title=title, artist=artist, duration=200)
    session.add(track)
    await session.commit()
    return track


async def fill_library(session, user: User, count: int) -> list[Track]:
    tracks = []
    for i in range(count):
        track = await make_track(session, title=f"Song {i:02d}")
        await add_to_library(session, user.id, track.id)
        tracks.append(track)
    return tracks


async def test_add_to_library_counts_and_rejects_duplicates(session):
    user = await make_user(session)
    track = await make_track(session, "Believer", "Imagine Dragons")

    assert await add_to_library(session, user.id, track.id) is True
    assert await add_to_library(session, user.id, track.id) is False
    assert await count_library_tracks(session, user.id) == 1


async def test_pagination_five_per_page(session):
    user = await make_user(session)
    await fill_library(session, user, count=7)

    page1 = await get_library_page(session, user.id, page=1)
    page2 = await get_library_page(session, user.id, page=2)

    assert len(page1) == 5
    assert len(page2) == 2
    assert {t.id for t in page1}.isdisjoint({t.id for t in page2})


async def test_search_matches_title_and_artist_only_in_own_library(session):
    user = await make_user(session)
    other = User(telegram_id=2)
    session.add(other)
    await session.commit()

    believer = await make_track(session, "Believer", "Imagine Dragons")
    thunder = await make_track(session, "Thunder", "Imagine Dragons")
    foreign = await make_track(session, "Believer Remix", "Someone")
    await add_to_library(session, user.id, believer.id)
    await add_to_library(session, user.id, thunder.id)
    await add_to_library(session, other.id, foreign.id)

    by_title = await search_library(session, user.id, "believer")
    by_artist = await search_library(session, user.id, "imagine")

    assert [t.id for t in by_title] == [believer.id]
    assert {t.id for t in by_artist} == {believer.id, thunder.id}


async def test_random_track_none_for_empty_library(session):
    user = await make_user(session)

    assert await get_random_track(session, user.id) is None


async def test_random_track_comes_from_own_library(session):
    user = await make_user(session)
    tracks = await fill_library(session, user, count=3)

    random_track = await get_random_track(session, user.id)

    assert random_track is not None
    assert random_track.id in {t.id for t in tracks}


async def test_remove_from_library_keeps_track_in_global_base(session):
    user = await make_user(session)
    track = await make_track(session, "Believer")
    await add_to_library(session, user.id, track.id)

    await remove_from_library(session, user.id, track.id)

    assert await count_library_tracks(session, user.id) == 0
    assert await session.get(Track, track.id) is not None

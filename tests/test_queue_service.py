from app.db.models import Playlist, Track, User
from app.services.library import add_to_library
from app.services.playlists import add_track_to_playlist, create_playlist
from app.services.queue import (
    get_library_batch,
    get_mix_batch,
    get_playlist_batch,
    get_search_batch,
)


async def make_user(session, telegram_id: int = 1) -> User:
    user = User(telegram_id=telegram_id)
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


async def test_mix_batch_excludes_recent(session):
    user = await make_user(session)
    tracks = await fill_library(session, user, count=8)
    recent = [t.id for t in tracks[:3]]

    batch = await get_mix_batch(session, user.id, recent)

    assert len(batch) == 5
    assert {t.id for t in batch}.isdisjoint(set(recent))


async def test_mix_batch_refills_when_everything_played(session):
    """Бесконечное радио: когда непослушанные закончились — добираем любыми."""
    user = await make_user(session)
    tracks = await fill_library(session, user, count=3)
    recent = [t.id for t in tracks]  # всё уже играло

    batch = await get_mix_batch(session, user.id, recent)

    assert len(batch) == 3


async def test_mix_batch_empty_library(session):
    user = await make_user(session)
    assert await get_mix_batch(session, user.id, []) == []


async def test_library_batch_offset_walks_whole_library(session):
    user = await make_user(session)
    await fill_library(session, user, count=7)

    first = await get_library_batch(session, user.id, offset=0)
    second = await get_library_batch(session, user.id, offset=5)
    third = await get_library_batch(session, user.id, offset=7)

    assert len(first) == 5
    assert len(second) == 2
    assert third == []
    assert {t.id for t in first}.isdisjoint({t.id for t in second})


async def test_playlist_batch_keeps_playlist_order(session):
    user = await make_user(session)
    playlist = await create_playlist(session, user.id, "Mix")
    tracks = [await make_track(session, f"T{i}") for i in range(3)]
    for track in tracks:
        await add_track_to_playlist(session, playlist.id, track.id)

    batch = await get_playlist_batch(session, playlist.id, offset=0)

    assert [t.id for t in batch] == [t.id for t in tracks]


async def test_search_batch_filters_and_paginates(session):
    await make_track(session, "Believer", "Imagine Dragons")
    await make_track(session, "Thunder", "Imagine Dragons")
    await make_track(session, "Unrelated", "Nobody")

    batch = await get_search_batch(session, "imagine", offset=0)
    rest = await get_search_batch(session, "imagine", offset=2)

    assert {t.title for t in batch} == {"Believer", "Thunder"}
    assert rest == []

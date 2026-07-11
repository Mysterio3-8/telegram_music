from app.db.models import PlaylistTrack, Track, User
from app.services.playlists import (
    add_track_to_playlist,
    count_playlist_tracks,
    create_playlist,
    delete_playlist,
    get_playlist,
    get_playlist_tracks_page,
    get_playlists_page,
    remove_track_from_playlist,
)
from app.services.users import count_playlists


async def make_user(session) -> User:
    user = User(telegram_id=1)
    session.add(user)
    await session.commit()
    return user


async def make_track(session, title: str) -> Track:
    track = Track(title=title, artist="Artist", duration=180)
    session.add(track)
    await session.commit()
    return track


async def test_create_and_count_playlists(session):
    user = await make_user(session)

    playlist = await create_playlist(session, user.id, "  Workout  ")

    assert playlist.title == "Workout"
    assert await count_playlists(session, user.id) == 1


async def test_playlists_pagination_five_per_page(session):
    user = await make_user(session)
    for i in range(7):
        await create_playlist(session, user.id, f"Playlist {i}")

    page1 = await get_playlists_page(session, user.id, page=1)
    page2 = await get_playlists_page(session, user.id, page=2)

    assert len(page1) == 5
    assert len(page2) == 2


async def test_add_track_keeps_order_and_rejects_duplicates(session):
    user = await make_user(session)
    playlist = await create_playlist(session, user.id, "Rock")
    first = await make_track(session, "First")
    second = await make_track(session, "Second")

    assert await add_track_to_playlist(session, playlist.id, first.id) is True
    assert await add_track_to_playlist(session, playlist.id, second.id) is True
    assert await add_track_to_playlist(session, playlist.id, first.id) is False

    tracks = await get_playlist_tracks_page(session, playlist.id, page=1)
    assert [t.id for t in tracks] == [first.id, second.id]
    assert await count_playlist_tracks(session, playlist.id) == 2


async def test_remove_track_from_playlist_keeps_track_in_base(session):
    user = await make_user(session)
    playlist = await create_playlist(session, user.id, "Rock")
    track = await make_track(session, "Song")
    await add_track_to_playlist(session, playlist.id, track.id)

    await remove_track_from_playlist(session, playlist.id, track.id)

    assert await count_playlist_tracks(session, playlist.id) == 0
    assert await session.get(Track, track.id) is not None


async def test_delete_playlist_removes_links_but_not_tracks(session):
    user = await make_user(session)
    playlist = await create_playlist(session, user.id, "Rock")
    track = await make_track(session, "Song")
    await add_track_to_playlist(session, playlist.id, track.id)

    await delete_playlist(session, playlist.id)

    assert await get_playlist(session, playlist.id) is None
    assert await session.get(PlaylistTrack, (playlist.id, track.id)) is None
    assert await session.get(Track, track.id) is not None

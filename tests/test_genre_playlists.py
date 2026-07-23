import pytest
from sqlalchemy import func, select

from app.db.models import Artist, Playlist, PlaylistTrack, Track, User
from app.services.genre_playlists import generate_genre_playlists
from app.services.genres import get_genre_by_slug, seed_genres, set_artist_genres


async def _seed_genre_with_tracks(session, count: int) -> None:
    await seed_genres(session)
    artist = Artist(name="DVRST", normalized_name="dvrst")
    session.add(artist)
    await session.commit()
    drift = await get_genre_by_slug(session, "drift-phonk")
    await set_artist_genres(session, artist.id, [drift.name])
    for i in range(count):
        session.add(Track(title=f"T{i}", artist="DVRST", duration=120))
    await session.commit()


@pytest.mark.asyncio
async def test_generate_skips_poor_genres(session):
    user = User(telegram_id=1)
    session.add(user)
    await session.commit()
    await _seed_genre_with_tracks(session, 3)  # ниже порога 10
    results = await generate_genre_playlists(session, user.id)
    assert results == []


@pytest.mark.asyncio
async def test_generate_and_refresh(session):
    user = User(telegram_id=1)
    session.add(user)
    await session.commit()
    await _seed_genre_with_tracks(session, 12)

    results = await generate_genre_playlists(session, user.id)
    # Drift Phonk + родители (Phonk, Электроника) наследуют треки — 3 подборки
    titles = {r.title for r in results}
    assert titles == {"Drift Phonk", "Phonk", "Электроника"}
    assert all(r.created and r.track_count == 12 for r in results)

    # Повторный прогон обновляет, не дублирует
    again = await generate_genre_playlists(session, user.id)
    assert all(not r.created for r in again)
    playlist_count = await session.scalar(select(func.count()).select_from(Playlist))
    assert playlist_count == 3
    drift_playlist = await session.scalar(
        select(Playlist).where(Playlist.title == "Drift Phonk")
    )
    links = await session.scalar(
        select(func.count()).select_from(PlaylistTrack).where(
            PlaylistTrack.playlist_id == drift_playlist.id
        )
    )
    assert links == 12

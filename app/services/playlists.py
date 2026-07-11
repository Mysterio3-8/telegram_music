from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import Playlist, PlaylistTrack, Track


async def get_playlists_page(session: AsyncSession, user_id: int, page: int) -> list[Playlist]:
    stmt = (
        select(Playlist)
        .where(Playlist.user_id == user_id)
        .order_by(Playlist.created_at.desc(), Playlist.id.desc())
        .offset((page - 1) * settings.page_size)
        .limit(settings.page_size)
    )
    return list((await session.scalars(stmt)).all())


async def get_all_playlists(session: AsyncSession, user_id: int) -> list[Playlist]:
    stmt = select(Playlist).where(Playlist.user_id == user_id).order_by(Playlist.title)
    return list((await session.scalars(stmt)).all())


async def create_playlist(session: AsyncSession, user_id: int, title: str) -> Playlist:
    playlist = Playlist(user_id=user_id, title=title.strip())
    session.add(playlist)
    await session.commit()
    return playlist


async def get_playlist(session: AsyncSession, playlist_id: int) -> Playlist | None:
    return await session.get(Playlist, playlist_id)


async def delete_playlist(session: AsyncSession, playlist_id: int) -> None:
    await session.execute(delete(PlaylistTrack).where(PlaylistTrack.playlist_id == playlist_id))
    playlist = await session.get(Playlist, playlist_id)
    if playlist is not None:
        await session.delete(playlist)
    await session.commit()


async def count_playlist_tracks(session: AsyncSession, playlist_id: int) -> int:
    count = await session.scalar(
        select(func.count())
        .select_from(PlaylistTrack)
        .where(PlaylistTrack.playlist_id == playlist_id)
    )
    return count or 0


async def get_playlist_tracks_page(
    session: AsyncSession, playlist_id: int, page: int
) -> list[Track]:
    stmt = (
        select(Track)
        .join(PlaylistTrack, PlaylistTrack.track_id == Track.id)
        .where(PlaylistTrack.playlist_id == playlist_id)
        .order_by(PlaylistTrack.position)
        .offset((page - 1) * settings.page_size)
        .limit(settings.page_size)
    )
    return list((await session.scalars(stmt)).all())


async def add_track_to_playlist(session: AsyncSession, playlist_id: int, track_id: int) -> bool:
    """Возвращает False, если трек уже есть в плейлисте."""
    existing = await session.get(PlaylistTrack, (playlist_id, track_id))
    if existing is not None:
        return False
    max_position = await session.scalar(
        select(func.max(PlaylistTrack.position)).where(PlaylistTrack.playlist_id == playlist_id)
    )
    session.add(
        PlaylistTrack(playlist_id=playlist_id, track_id=track_id, position=(max_position or 0) + 1)
    )
    await session.commit()
    return True


async def remove_track_from_playlist(
    session: AsyncSession, playlist_id: int, track_id: int
) -> None:
    entry = await session.get(PlaylistTrack, (playlist_id, track_id))
    if entry is not None:
        await session.delete(entry)
        await session.commit()

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import Track, UserLibrary


def _library_tracks(user_id: int):
    return (
        select(Track)
        .join(UserLibrary, UserLibrary.track_id == Track.id)
        .where(UserLibrary.user_id == user_id)
    )


async def get_library_page(session: AsyncSession, user_id: int, page: int) -> list[Track]:
    stmt = (
        _library_tracks(user_id)
        .order_by(UserLibrary.added_at.desc(), Track.id.desc())
        .offset((page - 1) * settings.page_size)
        .limit(settings.page_size)
    )
    return list((await session.scalars(stmt)).all())


async def search_library(session: AsyncSession, user_id: int, query: str) -> list[Track]:
    pattern = f"%{query.strip()}%"
    stmt = (
        _library_tracks(user_id)
        .where(or_(Track.title.ilike(pattern), Track.artist.ilike(pattern)))
        .order_by(Track.artist, Track.title)
        .limit(settings.library_search_limit)
    )
    return list((await session.scalars(stmt)).all())


async def get_random_track(session: AsyncSession, user_id: int) -> Track | None:
    stmt = _library_tracks(user_id).order_by(func.random()).limit(1)
    return await session.scalar(stmt)


async def get_track(session: AsyncSession, track_id: int) -> Track | None:
    return await session.get(Track, track_id)


async def update_track_meta(
    session: AsyncSession, track_id: int, title: str | None, artist: str | None
) -> Track | None:
    """Правка метаданных трека (админ). Сбрасывает meta_synced — при следующей
    выдаче файл будет перетегирован и переотправлен с новым именем."""
    track = await session.get(Track, track_id)
    if track is None:
        return None
    changed = False
    if title and title.strip() and title.strip() != track.title:
        track.title = title.strip()
        changed = True
    if artist and artist.strip() and artist.strip() != track.artist:
        track.artist = artist.strip()
        changed = True
    if changed:
        track.meta_synced = False
        await session.commit()
    return track


async def add_to_library(session: AsyncSession, user_id: int, track_id: int) -> bool:
    """Возвращает False, если трек уже был в библиотеке."""
    existing = await session.get(UserLibrary, (user_id, track_id))
    if existing is not None:
        return False
    session.add(UserLibrary(user_id=user_id, track_id=track_id))
    await session.commit()
    return True


async def remove_from_library(session: AsyncSession, user_id: int, track_id: int) -> None:
    entry = await session.get(UserLibrary, (user_id, track_id))
    if entry is not None:
        await session.delete(entry)
        await session.commit()

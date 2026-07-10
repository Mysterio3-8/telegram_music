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

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import Instrumental, Track


def _track_filter(query: str):
    pattern = f"%{query.strip()}%"
    return or_(Track.title.ilike(pattern), Track.artist.ilike(pattern))


async def search_tracks(
    session: AsyncSession, query: str, page: int, page_size: int | None = None
) -> tuple[list[Track], int]:
    """Поиск по общей базе. Возвращает (страница результатов, всего найдено).

    page_size переопределяется только Mini App (пачки до 100); бот всегда на дефолте.
    """
    size = page_size or settings.page_size
    where = _track_filter(query)
    total = await session.scalar(select(func.count()).select_from(Track).where(where)) or 0
    stmt = (
        select(Track)
        .where(where)
        .order_by(Track.artist, Track.title)
        .offset((page - 1) * size)
        .limit(size)
    )
    return list((await session.scalars(stmt)).all()), total


def _instrumental_filter(query: str):
    pattern = f"%{query.strip()}%"
    return or_(Instrumental.title.ilike(pattern), Instrumental.artist.ilike(pattern))


async def search_instrumentals(
    session: AsyncSession, query: str, page: int, page_size: int | None = None
) -> tuple[list[Instrumental], int]:
    size = page_size or settings.page_size
    where = _instrumental_filter(query)
    total = await session.scalar(select(func.count()).select_from(Instrumental).where(where)) or 0
    stmt = (
        select(Instrumental)
        .where(where)
        .order_by(Instrumental.artist, Instrumental.title)
        .offset((page - 1) * size)
        .limit(size)
    )
    return list((await session.scalars(stmt)).all()), total


async def get_instrumental(session: AsyncSession, instrumental_id: int) -> Instrumental | None:
    return await session.get(Instrumental, instrumental_id)

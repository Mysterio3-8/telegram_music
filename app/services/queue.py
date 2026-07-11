"""Очередь воспроизведения (SPEC: доработки, п.3 и п.9).

Telegram-клиент автоматически проигрывает следующее аудиосообщение в чате,
поэтому «очередь» — это пачка аудио, отправленных подряд. Здесь — только
выборка треков для очередной пачки; отправка — в handlers/delivery.py.
"""
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import PlaylistTrack, Track, UserLibrary


async def get_mix_batch(
    session: AsyncSession, user_id: int, exclude_ids: list[int], limit: int | None = None
) -> list[Track]:
    """Случайные треки библиотеки для режима «Микс», без недавно игравших.

    Если непослушанных не хватает — добираем любыми случайными (бесконечное радио).
    """
    limit = limit or settings.queue_batch_size
    base = (
        select(Track)
        .join(UserLibrary, UserLibrary.track_id == Track.id)
        .where(UserLibrary.user_id == user_id)
    )
    stmt = base.order_by(func.random()).limit(limit)
    if exclude_ids:
        stmt = base.where(Track.id.not_in(exclude_ids)).order_by(func.random()).limit(limit)
    tracks = list((await session.scalars(stmt)).all())
    if len(tracks) < limit and exclude_ids:
        refill = base.where(Track.id.not_in([t.id for t in tracks])).order_by(func.random()).limit(
            limit - len(tracks)
        )
        tracks += list((await session.scalars(refill)).all())
    return tracks


async def get_library_batch(
    session: AsyncSession, user_id: int, offset: int, limit: int | None = None
) -> list[Track]:
    stmt = (
        select(Track)
        .join(UserLibrary, UserLibrary.track_id == Track.id)
        .where(UserLibrary.user_id == user_id)
        .order_by(UserLibrary.added_at.desc(), Track.id.desc())
        .offset(offset)
        .limit(limit or settings.queue_batch_size)
    )
    return list((await session.scalars(stmt)).all())


async def get_playlist_batch(
    session: AsyncSession, playlist_id: int, offset: int, limit: int | None = None
) -> list[Track]:
    stmt = (
        select(Track)
        .join(PlaylistTrack, PlaylistTrack.track_id == Track.id)
        .where(PlaylistTrack.playlist_id == playlist_id)
        .order_by(PlaylistTrack.position)
        .offset(offset)
        .limit(limit or settings.queue_batch_size)
    )
    return list((await session.scalars(stmt)).all())


async def get_search_batch(
    session: AsyncSession, query: str, offset: int, limit: int | None = None
) -> list[Track]:
    pattern = f"%{query.strip()}%"
    stmt = (
        select(Track)
        .where(or_(Track.title.ilike(pattern), Track.artist.ilike(pattern)))
        .order_by(Track.artist, Track.title)
        .offset(offset)
        .limit(limit or settings.queue_batch_size)
    )
    return list((await session.scalars(stmt)).all())

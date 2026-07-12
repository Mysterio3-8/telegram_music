"""Загрузка минусов через админ-панель (TZ §11) — запись напрямую в Instrumental,
дедуп только внутри instrumentals (не пересекается с tracks, TZ §9)."""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Instrumental
from app.services.uploads import DUPLICATE_DURATION_TOLERANCE, AudioMeta


async def find_duplicate_instrumental(
    session: AsyncSession, title: str, artist: str, duration: int
) -> Instrumental | None:
    stmt = (
        select(Instrumental)
        .where(
            func.lower(Instrumental.title) == title.strip().lower(),
            func.lower(Instrumental.artist) == artist.strip().lower(),
            Instrumental.duration.between(
                duration - DUPLICATE_DURATION_TOLERANCE, duration + DUPLICATE_DURATION_TOLERANCE
            ),
        )
        .limit(1)
    )
    return await session.scalar(stmt)


async def create_admin_instrumental(
    session: AsyncSession, meta: AudioMeta, title: str, artist: str, source: str = "admin_manual"
) -> Instrumental:
    instrumental = Instrumental(
        title=title.strip(),
        artist=artist.strip(),
        duration=meta.duration,
        tg_file_id=meta.file_id,
        source=source,
    )
    session.add(instrumental)
    await session.commit()
    return instrumental

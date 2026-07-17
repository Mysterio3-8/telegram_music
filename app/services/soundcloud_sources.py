"""SoundCloud-источники минусов: постоянные, с автопроверкой новых битов.

Владелец кидает ссылку один раз — она сохраняется источником, ежедневный
таймер добирает только новое (дедуп в import_soundcloud_minuses).
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import SoundcloudSource


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def add_source(
    session: AsyncSession, url: str, title: str | None = None
) -> tuple[SoundcloudSource, bool]:
    """Возвращает (источник, создан_ли). Повторная ссылка — существующий источник."""
    clean = url.strip().rstrip("/")
    existing = await session.scalar(select(SoundcloudSource).where(SoundcloudSource.url == clean))
    if existing is not None:
        if existing.status != "active":
            existing.status = "active"
            await session.commit()
        return existing, False
    source = SoundcloudSource(url=clean, title=title, status="active")
    session.add(source)
    await session.commit()
    return source, True


async def list_sources(session: AsyncSession) -> list[SoundcloudSource]:
    return list((await session.scalars(select(SoundcloudSource).order_by(SoundcloudSource.id))).all())


async def mark_checked(
    session: AsyncSession, source_id: int, found: int, imported: int
) -> None:
    source = await session.get(SoundcloudSource, source_id)
    if source is None:
        return
    source.last_checked_at = _utcnow()
    source.found_count = found
    source.imported_count += imported
    await session.commit()


async def sources_due_for_check(session: AsyncSession) -> list[int]:
    """Активные источники, которые пора перепроверить (или ещё ни разу не сканились)."""
    threshold = _utcnow() - timedelta(days=settings.soundcloud_check_interval_days)
    stmt = select(SoundcloudSource.id).where(
        SoundcloudSource.status == "active",
        (SoundcloudSource.last_checked_at.is_(None)) | (SoundcloudSource.last_checked_at < threshold),
    )
    return list((await session.scalars(stmt)).all())

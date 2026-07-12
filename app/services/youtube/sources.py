from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import YoutubeImport, YoutubeSource
from app.services.youtube.downloader import VideoEntry


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def add_source(session: AsyncSession, url: str, title: str | None = None) -> YoutubeSource:
    source = YoutubeSource(url=url.strip(), title=title, status="active")
    session.add(source)
    await session.commit()
    return source


async def list_sources(session: AsyncSession) -> list[YoutubeSource]:
    stmt = select(YoutubeSource).order_by(YoutubeSource.id)
    return list((await session.scalars(stmt)).all())


async def get_source(session: AsyncSession, source_id: int) -> YoutubeSource | None:
    return await session.get(YoutubeSource, source_id)


async def set_source_status(session: AsyncSession, source_id: int, status: str) -> None:
    source = await session.get(YoutubeSource, source_id)
    if source is not None:
        source.status = status
        await session.commit()


async def delete_source(session: AsyncSession, source_id: int) -> None:
    """Удаляет источник и его очередь импортов. Импортированные треки остаются (§17)."""
    source = await session.get(YoutubeSource, source_id)
    if source is None:
        return
    await session.execute(
        YoutubeImport.__table__.delete().where(YoutubeImport.source_id == source_id)
    )
    await session.delete(source)
    await session.commit()


async def register_found_videos(
    session: AsyncSession, source_id: int, videos: list[VideoEntry]
) -> int:
    """Добавляет новые video_id в очередь (pending). Дубли отсекает уникальность source+video_id.
    Возвращает число реально добавленных задач."""
    if not videos:
        await _refresh_counts(session, source_id, found_delta=0)
        return 0

    rows = [
        {
            "source_id": source_id,
            "video_id": video.video_id,
            "video_title": video.title[:512],
            "status": "pending",
        }
        for video in videos
    ]
    stmt = sqlite_insert(YoutubeImport).values(rows).on_conflict_do_nothing(
        index_elements=["source_id", "video_id"]
    )
    result = await session.execute(stmt)
    await session.commit()
    added = result.rowcount if result.rowcount and result.rowcount > 0 else 0
    await _refresh_counts(session, source_id, found_delta=len(videos))
    return added


async def _refresh_counts(session: AsyncSession, source_id: int, found_delta: int) -> None:
    source = await session.get(YoutubeSource, source_id)
    if source is None:
        return
    total_found = await session.scalar(
        select(func.count()).select_from(YoutubeImport).where(YoutubeImport.source_id == source_id)
    )
    imported = await session.scalar(
        select(func.count())
        .select_from(YoutubeImport)
        .where(YoutubeImport.source_id == source_id, YoutubeImport.status == "imported")
    )
    source.found_count = total_found or 0
    source.imported_count = imported or 0
    source.last_checked_at = _utcnow()
    await session.commit()


async def pending_import_ids(session: AsyncSession, source_id: int) -> list[int]:
    stmt = (
        select(YoutubeImport.id)
        .where(YoutubeImport.source_id == source_id, YoutubeImport.status == "pending")
        .order_by(YoutubeImport.id)
    )
    return list((await session.scalars(stmt)).all())


async def requeue_stuck(session: AsyncSession) -> list[int]:
    """Возвращает в очередь задачи, оборванные аварийным завершением (§15)."""
    stmt = select(YoutubeImport).where(YoutubeImport.status.in_(("downloading", "processing")))
    stuck = list((await session.scalars(stmt)).all())
    for imp in stuck:
        imp.status = "pending"
    await session.commit()
    return [imp.id for imp in stuck]


async def sources_due_for_check(session: AsyncSession) -> list[int]:
    """ID активных источников, не проверявшихся дольше интервала (§11)."""
    threshold = _utcnow() - timedelta(days=settings.youtube_check_interval_days)
    stmt = select(YoutubeSource.id).where(
        YoutubeSource.status == "active",
        (YoutubeSource.last_checked_at.is_(None)) | (YoutubeSource.last_checked_at < threshold),
    )
    return list((await session.scalars(stmt)).all())

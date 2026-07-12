from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import TelegramChannelImport, TelegramChannelSource
from app.services.telegram_channel.scanner import AudioMessageRef


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def add_source(
    session: AsyncSession, channel: str, title: str | None = None
) -> TelegramChannelSource:
    source = TelegramChannelSource(channel=channel.strip(), title=title, status="active")
    session.add(source)
    await session.commit()
    return source


async def list_sources(session: AsyncSession) -> list[TelegramChannelSource]:
    stmt = select(TelegramChannelSource).order_by(TelegramChannelSource.id)
    return list((await session.scalars(stmt)).all())


async def get_source(session: AsyncSession, source_id: int) -> TelegramChannelSource | None:
    return await session.get(TelegramChannelSource, source_id)


async def set_source_status(session: AsyncSession, source_id: int, status: str) -> None:
    source = await session.get(TelegramChannelSource, source_id)
    if source is not None:
        source.status = status
        await session.commit()


async def delete_source(session: AsyncSession, source_id: int) -> None:
    """Удаляет источник и его очередь импортов. Импортированные треки остаются."""
    source = await session.get(TelegramChannelSource, source_id)
    if source is None:
        return
    await session.execute(
        TelegramChannelImport.__table__.delete().where(TelegramChannelImport.source_id == source_id)
    )
    await session.delete(source)
    await session.commit()


async def register_found_messages(
    session: AsyncSession, source_id: int, refs: list[AudioMessageRef]
) -> int:
    """Добавляет новые message_id в очередь (pending). Дубли отсекает уникальность
    source+message_id. Продвигает last_message_id, чтобы следующий скан запросил
    только более новые сообщения. Возвращает число реально добавленных задач."""
    if not refs:
        await _refresh_counts(session, source_id, advance_message_id=None)
        return 0

    rows = [
        {
            "source_id": source_id,
            "message_id": ref.message_id,
            "original_title": (ref.posted_title or ref.caption or "")[:512],
            "status": "pending",
        }
        for ref in refs
    ]
    stmt = sqlite_insert(TelegramChannelImport).values(rows).on_conflict_do_nothing(
        index_elements=["source_id", "message_id"]
    )
    result = await session.execute(stmt)
    await session.commit()
    added = result.rowcount if result.rowcount and result.rowcount > 0 else 0
    await _refresh_counts(session, source_id, advance_message_id=max(r.message_id for r in refs))
    return added


async def _refresh_counts(
    session: AsyncSession, source_id: int, advance_message_id: int | None
) -> None:
    source = await session.get(TelegramChannelSource, source_id)
    if source is None:
        return
    total_found = await session.scalar(
        select(func.count())
        .select_from(TelegramChannelImport)
        .where(TelegramChannelImport.source_id == source_id)
    )
    imported = await session.scalar(
        select(func.count())
        .select_from(TelegramChannelImport)
        .where(
            TelegramChannelImport.source_id == source_id,
            TelegramChannelImport.status == "imported",
        )
    )
    source.found_count = total_found or 0
    source.imported_count = imported or 0
    source.last_checked_at = _utcnow()
    if advance_message_id is not None and advance_message_id > source.last_message_id:
        source.last_message_id = advance_message_id
    await session.commit()


async def pending_import_ids(session: AsyncSession, source_id: int) -> list[int]:
    stmt = (
        select(TelegramChannelImport.id)
        .where(
            TelegramChannelImport.source_id == source_id,
            TelegramChannelImport.status == "pending",
        )
        .order_by(TelegramChannelImport.id)
    )
    return list((await session.scalars(stmt)).all())


async def requeue_stuck(session: AsyncSession) -> list[int]:
    """Возвращает в очередь задачи, оборванные аварийным завершением."""
    stmt = select(TelegramChannelImport).where(
        TelegramChannelImport.status.in_(("downloading", "processing"))
    )
    stuck = list((await session.scalars(stmt)).all())
    for imp in stuck:
        imp.status = "pending"
    await session.commit()
    return [imp.id for imp in stuck]


async def sources_due_for_check(session: AsyncSession) -> list[int]:
    """ID активных источников, не проверявшихся дольше интервала."""
    threshold = _utcnow() - timedelta(days=settings.telegram_channel_check_interval_days)
    stmt = select(TelegramChannelSource.id).where(
        TelegramChannelSource.status == "active",
        (TelegramChannelSource.last_checked_at.is_(None))
        | (TelegramChannelSource.last_checked_at < threshold),
    )
    return list((await session.scalars(stmt)).all())

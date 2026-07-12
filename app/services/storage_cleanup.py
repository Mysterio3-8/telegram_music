"""Очистка архивных копий на диске для треков, которые уже надёжно доступны
через tg_file_id (meta_synced=True). Архив на диске нужен только как страховка
на случай отсутствия tg_file_id — если он уже есть и подтверждён (актуальные
теги/имя), файл в storage/ — просто дубликат, занимающий место.
"""
import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Track
from app.storage.base import StorageBackend

logger = logging.getLogger(__name__)


def _reclaimable_where():
    return (
        Track.storage_path.is_not(None),
        Track.tg_file_id.is_not(None),
        Track.meta_synced.is_(True),
    )


async def count_reclaimable(session: AsyncSession) -> tuple[int, int]:
    """(число треков с архивом-дублем, сумма их file_size в байтах)."""
    count = await session.scalar(
        select(func.count()).select_from(Track).where(*_reclaimable_where())
    )
    total_bytes = await session.scalar(
        select(func.coalesce(func.sum(Track.file_size), 0)).where(*_reclaimable_where())
    )
    return count or 0, total_bytes or 0


async def reclaim_disk_space(session: AsyncSession, storage: StorageBackend) -> int:
    """Удаляет архивные копии для треков, уже надёжно доступных через
    tg_file_id. Возвращает число реально удалённых файлов."""
    stmt = select(Track).where(*_reclaimable_where())
    tracks = list((await session.scalars(stmt)).all())

    deleted = 0
    for track in tracks:
        try:
            storage.delete(f"tracks/{track.id}")
        except Exception:  # noqa: BLE001 — один сбойный файл не должен прерывать очистку
            logger.warning("Не удалось удалить архив track=%s", track.id, exc_info=True)
            continue
        track.storage_path = None
        deleted += 1

    await session.commit()
    return deleted

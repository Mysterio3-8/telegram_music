"""Очистка базы от не-музыки (доп. ТЗ): треки короче track_min_seconds или длиннее
track_max_seconds — джинглы, обрезки, подкасты, видео. По решению владельца такие
треки удаляются ПОЛНОСТЬЮ (осознанное исключение из инварианта «трек не удаляется»):
файл из хранилища + все связи + сама запись."""
import logging
from dataclasses import dataclass

from sqlalchemy import delete, false, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.db.models import (
    Lyrics,
    PlaylistTrack,
    TelegramChannelImport,
    Track,
    TrackEvent,
    Upload,
    UserLibrary,
    YoutubeImport,
)
from app.storage.base import StorageBackend

logger = logging.getLogger(__name__)


def _junk_condition():
    # Границы 0 = лимит снят: без них понятие «не-музыка по длительности» не определено
    conditions = []
    if settings.track_min_seconds:
        conditions.append(Track.duration < settings.track_min_seconds)
    if settings.track_max_seconds:
        conditions.append(Track.duration > settings.track_max_seconds)
    return or_(*conditions) if conditions else false()


@dataclass(frozen=True)
class JunkStats:
    count: int
    total_bytes: int  # по file_size, где он известен


async def count_junk_tracks(session: AsyncSession) -> JunkStats:
    rows = (await session.execute(select(Track.id, Track.file_size).where(_junk_condition()))).all()
    return JunkStats(
        count=len(rows),
        total_bytes=sum(size for _, size in rows if size),
    )


async def list_junk_tracks(session: AsyncSession, limit: int = 15) -> list[Track]:
    stmt = select(Track).where(_junk_condition()).order_by(Track.duration.desc()).limit(limit)
    return list((await session.scalars(stmt)).all())


async def delete_junk_tracks(session: AsyncSession, storage: StorageBackend) -> int:
    """Удаляет мусорные треки целиком. Возвращает число удалённых."""
    tracks = list((await session.scalars(select(Track).where(_junk_condition()))).all())
    if not tracks:
        return 0
    ids = [t.id for t in tracks]

    # Файлы из хранилища — до удаления записей (ошибка файла не роняет чистку)
    for track in tracks:
        if track.storage_path:
            try:
                await run_in_threadpool(storage.delete, f"tracks/{track.id}")
            except Exception:  # noqa: BLE001
                logger.warning("Не удалить файл track=%s из хранилища", track.id, exc_info=True)

    # Связи, затем сами треки
    await session.execute(delete(UserLibrary).where(UserLibrary.track_id.in_(ids)))
    await session.execute(delete(PlaylistTrack).where(PlaylistTrack.track_id.in_(ids)))
    await session.execute(delete(TrackEvent).where(TrackEvent.track_id.in_(ids)))
    await session.execute(delete(Lyrics).where(Lyrics.track_id.in_(ids)))
    await session.execute(delete(Upload).where(Upload.track_id.in_(ids)))
    await session.execute(
        update(YoutubeImport).where(YoutubeImport.track_id.in_(ids)).values(track_id=None)
    )
    await session.execute(
        update(TelegramChannelImport)
        .where(TelegramChannelImport.track_id.in_(ids))
        .values(track_id=None)
    )
    await session.execute(delete(Track).where(Track.id.in_(ids)))
    await session.commit()
    logger.info("Очистка не-музыки: удалено %s треков", len(ids))
    return len(ids)

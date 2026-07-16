"""Статистика проекта для админ-панели + запись событий прослушивания/скачивания."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Track, TrackEvent, User
from app.services.storage_cleanup import count_reclaimable


def _utcnow() -> datetime:
    # Наивный UTC — как в premium.py: SQLite хранит datetime без таймзоны
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def record_event(session: AsyncSession, user_id: int, track_id: int, event: str) -> None:
    """event: listen | download. Коммитит."""
    session.add(TrackEvent(user_id=user_id, track_id=track_id, event=event))
    await session.commit()


@dataclass(frozen=True)
class ProjectStats:
    users_total: int
    users_new_day: int
    users_active_all_time: int  # хоть раз заходили (last_login проставлен)
    premium_active: int
    tracks_total: int  # все треки, доступные для прослушивания — независимо от хранилища
    archived_on_disk: int  # сколько из них ещё держат архивную копию (storage_path)
    reclaimable_count: int  # архив-дубли: tg_file_id уже есть и подтверждён — можно удалить
    reclaimable_bytes: int
    junk_count: int  # не похоже на музыку: короче track_min_seconds / длиннее track_max_seconds


async def _count(session: AsyncSession, stmt) -> int:
    return (await session.scalar(stmt)) or 0


async def collect_stats(session: AsyncSession) -> ProjectStats:
    now = _utcnow()
    day_ago = now - timedelta(days=1)

    def users_where(*conditions):
        return select(func.count()).select_from(User).where(*conditions)

    from app.services.catalog_cleanup import count_junk_tracks

    reclaimable_count, reclaimable_bytes = await count_reclaimable(session)
    junk = await count_junk_tracks(session)

    return ProjectStats(
        users_total=await _count(session, users_where()),
        users_new_day=await _count(session, users_where(User.created_at >= day_ago)),
        users_active_all_time=await _count(session, users_where(User.last_login.is_not(None))),
        premium_active=await _count(session, users_where(User.premium.is_(True))),
        tracks_total=await _count(session, select(func.count()).select_from(Track)),
        archived_on_disk=await _count(
            session, select(func.count()).select_from(Track).where(Track.storage_path.is_not(None))
        ),
        reclaimable_count=reclaimable_count,
        reclaimable_bytes=reclaimable_bytes,
        junk_count=junk.count,
    )

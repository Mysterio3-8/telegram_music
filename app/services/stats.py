"""Статистика проекта для админ-панели + запись событий прослушивания/скачивания."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Playlist, Track, TrackEvent, Upload, User
from app.services.storage_cleanup import count_reclaimable

TOP_TRACKS_LIMIT = 5


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
    users_new_week: int
    users_active_day: int
    users_active_week: int
    premium_active: int
    tracks_total: int  # все треки, доступные для прослушивания — независимо от хранилища
    archived_on_disk: int  # сколько из них ещё держат архивную копию (storage_path)
    reclaimable_count: int  # архив-дубли: tg_file_id уже есть и подтверждён — можно удалить
    reclaimable_bytes: int
    uploads_total: int
    playlists_total: int
    listens_total: int
    listens_day: int
    downloads_total: int
    downloads_day: int
    top_tracks: list[tuple[Track, int]]  # (трек, число событий)


async def _count(session: AsyncSession, stmt) -> int:
    return (await session.scalar(stmt)) or 0


async def collect_stats(session: AsyncSession) -> ProjectStats:
    now = _utcnow()
    day_ago = now - timedelta(days=1)
    week_ago = now - timedelta(days=7)

    def users_where(*conditions):
        return select(func.count()).select_from(User).where(*conditions)

    def events_where(*conditions):
        return select(func.count()).select_from(TrackEvent).where(*conditions)

    top_stmt = (
        select(Track, func.count(TrackEvent.id).label("plays"))
        .join(TrackEvent, TrackEvent.track_id == Track.id)
        .group_by(Track.id)
        .order_by(func.count(TrackEvent.id).desc())
        .limit(TOP_TRACKS_LIMIT)
    )
    top_tracks = [(track, plays) for track, plays in (await session.execute(top_stmt)).all()]
    reclaimable_count, reclaimable_bytes = await count_reclaimable(session)

    return ProjectStats(
        users_total=await _count(session, users_where()),
        users_new_day=await _count(session, users_where(User.created_at >= day_ago)),
        users_new_week=await _count(session, users_where(User.created_at >= week_ago)),
        users_active_day=await _count(session, users_where(User.last_login >= day_ago)),
        users_active_week=await _count(session, users_where(User.last_login >= week_ago)),
        premium_active=await _count(session, users_where(User.premium.is_(True))),
        tracks_total=await _count(session, select(func.count()).select_from(Track)),
        archived_on_disk=await _count(
            session, select(func.count()).select_from(Track).where(Track.storage_path.is_not(None))
        ),
        reclaimable_count=reclaimable_count,
        reclaimable_bytes=reclaimable_bytes,
        uploads_total=await _count(session, select(func.count()).select_from(Upload)),
        playlists_total=await _count(session, select(func.count()).select_from(Playlist)),
        listens_total=await _count(session, events_where(TrackEvent.event == "listen")),
        listens_day=await _count(
            session, events_where(TrackEvent.event == "listen", TrackEvent.created_at >= day_ago)
        ),
        downloads_total=await _count(session, events_where(TrackEvent.event == "download")),
        downloads_day=await _count(
            session, events_where(TrackEvent.event == "download", TrackEvent.created_at >= day_ago)
        ),
        top_tracks=top_tracks,
    )

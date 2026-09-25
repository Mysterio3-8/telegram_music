"""Статистика проекта для админ-панели + запись событий прослушивания/скачивания."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select, union
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Artist, SearchQuery, Track, TrackEvent, User
from app.services.storage_cleanup import count_reclaimable


def _utcnow() -> datetime:
    # Наивный UTC — как в premium.py: SQLite хранит datetime без таймзоны
    return datetime.now(timezone.utc).replace(tzinfo=None)


# Антинакрутка: одно и то же прослушивание засчитывается не чаще, чем раз в это
# окно — иначе можно накрутить статистику и нафармить дни Premium за достижения.
LISTEN_DEDUP_SECONDS = 30


async def record_event(
    session: AsyncSession, user_id: int, track_id: int, event: str, source: str = "unknown"
) -> None:
    """event: listen | download. Коммитит.
    Для listen — дедуп: повтор того же трека в пределах LISTEN_DEDUP_SECONDS не считается.
    source — откуда (bot | miniapp | worker): пишется в журнал аналитики тем же коммитом."""
    if event == "listen":
        recent = await session.scalar(
            select(func.count())
            .select_from(TrackEvent)
            .where(
                TrackEvent.user_id == user_id,
                TrackEvent.track_id == track_id,
                TrackEvent.event == "listen",
                TrackEvent.created_at >= _utcnow() - timedelta(seconds=LISTEN_DEDUP_SECONDS),
            )
        )
        if recent:
            return
    session.add(TrackEvent(user_id=user_id, track_id=track_id, event=event))
    from app.services.analytics import build_event

    session.add(build_event(event, source=source, user_id=user_id, track_id=track_id))
    await session.commit()


async def update_listen_seconds(
    session: AsyncSession, user_id: int, track_id: int, seconds: int
) -> None:
    """Дописывает реально прослушанные секунды к последнему событию listen.

    Клиент присылает это, когда трек кончился или его переключили. Обновляем, а
    не добавляем: одно прослушивание — одно событие, иначе счётчик прослушиваний
    удваивался бы на каждом треке.

    ⚠️ Берём только событие не старше часа: если человек вернулся к треку через
    неделю, дописывать секунды в прошлое нельзя.
    """
    if seconds <= 0:
        return
    event = await session.scalar(
        select(TrackEvent)
        .where(
            TrackEvent.user_id == user_id,
            TrackEvent.track_id == track_id,
            TrackEvent.event == "listen",
            TrackEvent.created_at >= _utcnow() - timedelta(hours=1),
        )
        .order_by(TrackEvent.created_at.desc())
        .limit(1)
    )
    if event is None:
        return
    # Максимум, а не перезапись: повторное сообщение о том же треке не должно
    # укорачивать уже засчитанное (человек мог доиграть и перемотать назад).
    event.seconds = max(event.seconds or 0, seconds)
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
    artists_total: int  # артистов-сущностей в каталоге (цель массового парсера — 10k)
    # Живой прогон 25.09: админка писала «все доступны для прослушивания», а у
    # 182 из 8871 не было ни file_id, ни архива. И «активных за всё время» было
    # всегда равно числу пользователей — ничего не говорило.
    tracks_playable: int = 0  # есть file_id или архив — играет сразу
    users_active_week: int = 0  # искали или слушали за 7 дней


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
        # Только реально активные: флаг premium мог остаться у истёкших до refresh
        premium_active=await _count(
            session, users_where(User.premium.is_(True), User.premium_until > now)
        ),
        tracks_total=await _count(session, select(func.count()).select_from(Track)),
        archived_on_disk=await _count(
            session, select(func.count()).select_from(Track).where(Track.storage_path.is_not(None))
        ),
        reclaimable_count=reclaimable_count,
        reclaimable_bytes=reclaimable_bytes,
        junk_count=junk.count,
        artists_total=await _count(session, select(func.count()).select_from(Artist)),
        tracks_playable=await _count(
            session,
            select(func.count())
            .select_from(Track)
            .where(or_(Track.tg_file_id.is_not(None), Track.storage_path.is_not(None))),
        ),
        users_active_week=await _count(
            session,
            select(func.count()).select_from(
                union(
                    select(TrackEvent.user_id).where(TrackEvent.created_at >= now - timedelta(days=7)),
                    select(SearchQuery.user_id).where(
                        SearchQuery.created_at >= now - timedelta(days=7),
                        SearchQuery.user_id.is_not(None),
                    ),
                ).subquery()
            ),
        ),
    )

"""Очистка базы от не-музыки (доп. ТЗ): треки короче track_min_seconds или длиннее
track_max_seconds — джинглы, обрезки, подкасты, видео. По решению владельца такие
треки удаляются ПОЛНОСТЬЮ (осознанное исключение из инварианта «трек не удаляется»):
файл из хранилища + все связи + сама запись."""
import logging
from dataclasses import dataclass

from sqlalchemy import and_, delete, false, or_, select, update
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


# Клипы/видео с YouTube («кишлак» по словам владельца): чистим по маркерам в
# названии. is_probably_junk — регексом в Python; для SQL берём ILIKE-паттерны.
_CLIP_MARKERS = ("%клип%", "%премьера%", "%official video%", "%music video%", "%лирик%", "%видеоклип%")


def _clip_condition():
    from sqlalchemy import or_ as _or

    return _or(*[Track.title.ilike(p) for p in _CLIP_MARKERS])


# Профиль чистки под живой поиск (решение владельца 2026-08-02). Каталог мы больше
# не копим, поэтому из него уходит то, что заведомо не музыка или бесполезно:
#   клипы — мусор ушедшего YouTube-парсера;
#   длиннее 15 минут — подкасты и часовые миксы;
#   без обложки — наследие массовой закачки: в Mini App такой трек выглядит пустым,
#   а перезалить его живым поиском дешевле, чем восстанавливать обложку.
# Короткие треки СПЕЦИАЛЬНО не трогаем: нижний порог поиска снят ради андеграунда,
# и удалять из базы то, что поиск теперь считает валидным, было бы противоречиво.
STALE_MAX_SECONDS = 900


def _stale_condition(keep_user_tracks: bool = True):
    """keep_user_tracks — не трогать то, что человек добавил себе в плейлист или
    библиотеку. Замер прода 2026-08-02: без защиты чистка уносила 2423 трека из
    2610 плейлистных, то есть 93% всего, что люди себе собрали. Живой поиск такие
    треки найдёт заново, но ПЛЕЙЛИСТ он не восстановит — там останется дыра."""
    stale = or_(
        _clip_condition(),
        Track.duration > STALE_MAX_SECONDS,
        Track.cover_url.is_(None),
        Track.cover_url == "",
    )
    if not keep_user_tracks:
        return stale
    return and_(
        stale,
        ~Track.id.in_(select(PlaylistTrack.track_id)),
        ~Track.id.in_(select(UserLibrary.track_id)),
    )


async def count_stale_tracks(session: AsyncSession) -> dict[str, int]:
    """Сколько треков попадёт под чистку, с разбивкой по причинам. Считается ДО
    удаления: операция необратимая, владелец должен видеть числа заранее."""
    from sqlalchemy import func

    async def total(condition) -> int:
        return await session.scalar(
            select(func.count()).select_from(Track).where(condition)
        ) or 0

    return {
        "clips": await total(_clip_condition()),
        "too_long": await total(Track.duration > STALE_MAX_SECONDS),
        "no_cover": await total(or_(Track.cover_url.is_(None), Track.cover_url == "")),
        "total": await total(_stale_condition(keep_user_tracks=False)),
        "protected": await total(_stale_condition(keep_user_tracks=True)),
    }


async def delete_stale_tracks(
    session: AsyncSession, storage: StorageBackend, keep_user_tracks: bool = True
) -> int:
    """Удаляет шлак целиком: файл + связи + запись. Возвращает число удалённых."""
    stmt = select(Track).where(_stale_condition(keep_user_tracks))
    return await _delete_tracks(session, storage, list((await session.scalars(stmt)).all()))


async def drop_fingerprints(session: AsyncSession) -> int:
    """Стирает отпечатки: они нужны были массовому парсеру для дедупа, а живому
    поиску не нужны — при этом их индекс весит 128 МБ, почти как вся таблица."""
    result = await session.execute(
        update(Track).where(Track.fingerprint.is_not(None)).values(fingerprint=None)
    )
    await session.commit()
    return result.rowcount or 0


@dataclass(frozen=True)
class JunkStats:
    count: int
    total_bytes: int  # по file_size, где он известен


async def count_clip_tracks(session: AsyncSession) -> int:
    from sqlalchemy import func

    return await session.scalar(
        select(func.count()).select_from(Track).where(_clip_condition())
    ) or 0


async def delete_clip_tracks(session: AsyncSession, storage: StorageBackend) -> int:
    """Удаляет клипы/видео (мусор с YouTube) по маркерам в названии."""
    tracks = list((await session.scalars(select(Track).where(_clip_condition()))).all())
    return await _delete_tracks(session, storage, tracks)


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
    return await _delete_tracks(session, storage, tracks)


async def _delete_tracks(session: AsyncSession, storage: StorageBackend, tracks: list[Track]) -> int:
    """Удаляет треки целиком: файл + все связи + запись. Возвращает число удалённых."""
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

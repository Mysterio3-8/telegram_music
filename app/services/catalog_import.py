from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Instrumental, Track, Upload, UserLibrary
from app.importers.base import ImportItem
from app.services.fingerprint import compute_fingerprint_from_bytes
from app.services.uploads import DUPLICATE_DURATION_TOLERANCE, find_by_fingerprint, find_duplicate
from app.storage.base import StorageBackend


async def import_track(
    session: AsyncSession, storage: StorageBackend, item: ImportItem
) -> bool:
    """Импортирует трек в общую базу. Возвращает True, если создан новый (False — дубликат)."""
    fingerprint = compute_fingerprint_from_bytes(item.data, suffix=f".{item.file_format or 'audio'}")

    if fingerprint and await find_by_fingerprint(session, fingerprint) is not None:
        return False
    if await find_duplicate(session, item.title, item.artist, item.duration) is not None:
        return False

    bitrate = None
    if item.duration > 0:
        bitrate = round(len(item.data) * 8 / item.duration / 1000)
    track = Track(
        title=item.title,
        artist=item.artist,
        duration=item.duration,
        bitrate=bitrate,
        file_size=len(item.data),
        format=item.file_format,
        fingerprint=fingerprint,
    )
    session.add(track)
    await session.flush()
    track.storage_path = storage.save(f"tracks/{track.id}", item.data)
    await session.commit()
    return True


async def _instrumental_duplicate(
    session: AsyncSession, item: ImportItem, fingerprint: str | None
) -> bool:
    if fingerprint:
        found = await session.scalar(
            select(Instrumental).where(Instrumental.fingerprint == fingerprint).limit(1)
        )
        if found is not None:
            return True
    metadata_dup = await session.scalar(
        select(Instrumental)
        .where(
            func.lower(Instrumental.title) == item.title.lower(),
            func.lower(Instrumental.artist) == item.artist.lower(),
            Instrumental.duration.between(
                item.duration - DUPLICATE_DURATION_TOLERANCE,
                item.duration + DUPLICATE_DURATION_TOLERANCE,
            ),
        )
        .limit(1)
    )
    return metadata_dup is not None


async def import_instrumental(
    session: AsyncSession, storage: StorageBackend, item: ImportItem
) -> bool:
    fingerprint = compute_fingerprint_from_bytes(item.data, suffix=f".{item.file_format or 'audio'}")
    if await _instrumental_duplicate(session, item, fingerprint):
        return False

    instrumental = Instrumental(
        title=item.title,
        artist=item.artist,
        duration=item.duration,
        fingerprint=fingerprint,
    )
    session.add(instrumental)
    await session.flush()
    instrumental.storage_path = storage.save(f"instrumentals/{instrumental.id}", item.data)
    await session.commit()
    return True


async def import_user_track(
    session: AsyncSession, storage: StorageBackend, user_id: int, item: ImportItem
) -> Track:
    """Загрузка трека через API: дедуп, создание в базе, привязка к библиотеке пользователя."""
    fingerprint = compute_fingerprint_from_bytes(item.data, suffix=f".{item.file_format or 'audio'}")

    track = None
    if fingerprint:
        track = await find_by_fingerprint(session, fingerprint)
    if track is None:
        track = await find_duplicate(session, item.title, item.artist, item.duration)

    if track is None:
        bitrate = round(len(item.data) * 8 / item.duration / 1000) if item.duration > 0 else None
        track = Track(
            title=item.title,
            artist=item.artist,
            duration=item.duration,
            bitrate=bitrate,
            file_size=len(item.data),
            format=item.file_format,
            fingerprint=fingerprint,
        )
        session.add(track)
        await session.flush()
        track.storage_path = storage.save(f"tracks/{track.id}", item.data)

    if await session.get(UserLibrary, (user_id, track.id)) is None:
        session.add(UserLibrary(user_id=user_id, track_id=track.id))
    session.add(Upload(user_id=user_id, track_id=track.id))
    await session.commit()
    return track

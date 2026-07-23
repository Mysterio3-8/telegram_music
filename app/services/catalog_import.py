import logging

from aiogram import Bot
from aiogram.types import BufferedInputFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Instrumental, Track, Upload, UserLibrary
from app.importers.base import ImportItem
from app.services.artist_binding import resolve_artist_id
from app.services.fingerprint import compute_fingerprint_from_bytes
from app.services.track_meta import build_filename, embed_cover, retag_audio
from app.services.uploads import DUPLICATE_DURATION_TOLERANCE, find_by_fingerprint, find_duplicate
from app.storage.base import StorageBackend

logger = logging.getLogger(__name__)


def _seed_cache(storage_key: str, data: bytes) -> None:
    """Постоянный архив на диске НЕ ведём (решение владельца: диск не копить) —
    байты заминченного файла сеются в LRU-кэш стриминга: свежие треки играют
    в Mini App мгновенно и без Bot API (важно для >20 МБ), кэш сам вытесняет
    старое в пределах AUDIO_CACHE_MAX_MB. S3 задан → пишем в S3 (диск не наш)."""
    from app.config import settings

    try:
        if settings.s3_endpoint_url and settings.s3_bucket:
            from app.storage import get_storage

            get_storage().save(storage_key, data)
            return
        from app.services.audio_cache import cache_put

        cache_put(storage_key, data)
    except Exception:  # noqa: BLE001
        logger.warning("Не удалось положить %s в кэш", storage_key, exc_info=True)


async def import_track_detailed(
    session: AsyncSession, storage: StorageBackend, item: ImportItem
) -> tuple[Track, bool]:
    """Импортирует трек в общую базу. Возвращает (трек, создан_ли_новый).
    При дубликате (по отпечатку или метаданным) возвращает найденный трек и False."""
    fingerprint = compute_fingerprint_from_bytes(item.data, suffix=f".{item.file_format or 'audio'}")

    if fingerprint:
        existing = await find_by_fingerprint(session, fingerprint)
        if existing is not None:
            return existing, False
    metadata_dup = await find_duplicate(session, item.title, item.artist, item.duration)
    if metadata_dup is not None:
        return metadata_dup, False

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
        artist_id=await resolve_artist_id(session, item.artist),
    )
    session.add(track)
    await session.flush()
    track.storage_path = storage.save(f"tracks/{track.id}", item.data)
    await session.commit()
    return track, True


async def import_track(
    session: AsyncSession, storage: StorageBackend, item: ImportItem
) -> bool:
    """Импортирует трек в общую базу. True — создан новый (False — дубликат)."""
    _, created = await import_track_detailed(session, storage, item)
    return created


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


async def find_existing_instrumental(
    session: AsyncSession, fingerprint: str | None, title: str, artist: str, duration: int
) -> Instrumental | None:
    if fingerprint:
        found = await session.scalar(
            select(Instrumental).where(Instrumental.fingerprint == fingerprint).limit(1)
        )
        if found is not None:
            return found
    return await session.scalar(
        select(Instrumental)
        .where(
            func.lower(Instrumental.title) == title.strip().lower(),
            func.lower(Instrumental.artist) == artist.strip().lower(),
            Instrumental.duration.between(
                duration - DUPLICATE_DURATION_TOLERANCE,
                duration + DUPLICATE_DURATION_TOLERANCE,
            ),
        )
        .limit(1)
    )


async def import_instrumental_via_telegram_mint(
    session: AsyncSession,
    bot: Bot,
    *,
    title: str,
    artist: str,
    duration: int,
    file_format: str | None,
    data: bytes,
    fingerprint: str | None,
    archive_chat_id: int,
    source: str,
) -> tuple[Instrumental, bool]:
    """Зеркало import_via_telegram_mint для минусов: дедуп только среди
    instrumentals (TZ §9), файл минтится через бота + архивная копия в хранилище.
    Возвращает (минус, создан_ли_новый)."""
    existing = await find_existing_instrumental(session, fingerprint, title, artist, duration)
    if existing is not None:
        return existing, False

    tagged = retag_audio(data, file_format, title, artist)
    sent = await bot.send_audio(
        archive_chat_id,
        BufferedInputFile(tagged, filename=build_filename(artist, title, file_format)),
        title=title,
        performer=artist,
        duration=duration or None,
    )
    instrumental = Instrumental(
        title=title.strip(),
        artist=artist.strip(),
        duration=duration,
        fingerprint=fingerprint,
        tg_file_id=sent.audio.file_id,
        source=source,
    )
    session.add(instrumental)
    await session.commit()
    _seed_cache(f"instrumentals/{instrumental.id}", tagged)
    return instrumental, True


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
            artist_id=await resolve_artist_id(session, item.artist),
        )
        session.add(track)
        await session.flush()
        track.storage_path = storage.save(f"tracks/{track.id}", item.data)

    if await session.get(UserLibrary, (user_id, track.id)) is None:
        session.add(UserLibrary(user_id=user_id, track_id=track.id))
    session.add(Upload(user_id=user_id, track_id=track.id))
    await session.commit()
    return track


async def find_existing_track(
    session: AsyncSession, fingerprint: str | None, title: str, artist: str, duration: int
) -> Track | None:
    """Дедуп-проверка без побочных эффектов: сначала по отпечатку, потом по метаданным."""
    if fingerprint:
        existing = await find_by_fingerprint(session, fingerprint)
        if existing is not None:
            return existing
    return await find_duplicate(session, title, artist, duration)


async def create_track_from_telegram(
    session: AsyncSession,
    *,
    title: str,
    artist: str,
    duration: int,
    file_format: str | None,
    file_size: int,
    fingerprint: str | None,
    tg_file_id: str,
    cover_url: str | None = None,
    album: str | None = None,
) -> Track:
    """Создаёт трек БЕЗ архивной копии на диске — файл уже заминчен через бота
    (tg_file_id валиден сразу), сохраняется только ссылка. Дедуп — забота вызывающей
    стороны (find_existing_track), чтобы не грузить в Telegram то, что уже есть."""
    bitrate = round(file_size * 8 / duration / 1000) if duration > 0 else None
    track = Track(
        title=title,
        artist=artist,
        artist_id=await resolve_artist_id(session, artist),
        album=album or None,
        duration=duration,
        bitrate=bitrate,
        file_size=file_size,
        format=file_format,
        fingerprint=fingerprint,
        tg_file_id=tg_file_id,
        cover_url=cover_url or None,
        meta_synced=True,
    )
    session.add(track)
    await session.commit()
    return track


async def import_via_telegram_mint(
    session: AsyncSession,
    bot: Bot,
    *,
    title: str,
    artist: str,
    duration: int,
    file_format: str | None,
    data: bytes,
    fingerprint: str | None,
    archive_chat_id: int,
    cover: bytes = b"",
    cover_url: str | None = None,
    album: str | None = None,
) -> tuple[Track, bool]:
    """Дедуп; если трек новый — перетегирует, вшивает обложку, отправляет через
    бота (единственный способ заминтить file_id — реально отправить файл через
    Bot API) и кладёт архивную копию в хранилище: стрим Mini App не упирается в
    лимит Bot API 20 МБ. Общая точка для YouTube- и Telegram-канал-импортёров.
    Возвращает (трек, создан_ли_новый)."""
    track = await find_existing_track(session, fingerprint, title, artist, duration)
    if track is not None:
        return track, False

    tagged = retag_audio(data, file_format, title, artist)
    if cover:
        tagged = embed_cover(tagged, file_format, cover)
    sent = await bot.send_audio(
        archive_chat_id,
        BufferedInputFile(tagged, filename=build_filename(artist, title, file_format)),
        title=title,
        performer=artist,
        duration=duration or None,
    )
    track = await create_track_from_telegram(
        session,
        title=title,
        artist=artist,
        duration=duration,
        file_format=file_format,
        file_size=len(tagged),
        fingerprint=fingerprint,
        tg_file_id=sent.audio.file_id,
        cover_url=cover_url,
        album=album,
    )
    _seed_cache(f"tracks/{track.id}", tagged)
    return track, True

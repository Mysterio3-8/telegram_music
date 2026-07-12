"""Импорт одной YouTube-публикации в общую базу треков (доп. ТЗ, §7-§10).

Скачивание → разбор названия → запись ID3-тегов → отпечаток/дедуп → трек в базе.
Файл сохраняется уже с корректными тегами (§8). Дубликаты по video_id отсекаются
уникальным ограничением, по содержимому — отпечатком/метаданными в catalog_import.
"""
import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import YoutubeImport, YoutubeSource
from app.importers.base import ImportItem
from app.services.catalog_import import import_track_detailed
from app.services.track_meta import retag_audio
from app.services.youtube.downloader import download_audio
from app.services.youtube.metadata import parse_title
from app.storage import get_storage

logger = logging.getLogger(__name__)


class ImportError_(Exception):
    """Временная ошибка импорта — задача должна быть повторена."""


async def process_import(session: AsyncSession, import_id: int) -> str:
    """Обрабатывает одну задачу. Возвращает финальный статус (imported/skipped).
    Кидает исключение при временной ошибке — воркер повторит попытку."""
    imp = await session.get(YoutubeImport, import_id)
    if imp is None:
        return "skipped"
    if imp.status == "imported":
        return "imported"
    source = await session.get(YoutubeSource, imp.source_id)
    fallback_artist = (source.title if source else None) or "Unknown"

    imp.status = "downloading"
    imp.attempts += 1
    await session.commit()

    audio = download_audio(imp.video_id)
    if audio is None:
        raise ImportError_(f"yt-dlp не вернул аудио для {imp.video_id}")

    imp.status = "processing"
    await session.commit()

    artist, title = parse_title(audio.video_title, fallback_artist)
    tagged = retag_audio(audio.data, audio.file_format, title, artist)
    item = ImportItem(
        title=title,
        artist=artist,
        duration=audio.duration,
        data=tagged,
        file_format=audio.file_format,
    )
    track, _created = await import_track_detailed(session, get_storage(), item)

    imp.detected_title = title[:256]
    imp.detected_artist = artist[:256]
    imp.video_title = audio.video_title[:512]
    imp.track_id = track.id
    imp.status = "imported"
    imp.last_error = None
    imp.imported_at = datetime.now(timezone.utc).replace(tzinfo=None)
    await session.commit()
    logger.info("YouTube импорт video=%s → track=%s (%s — %s)", imp.video_id, track.id, artist, title)
    return "imported"


async def mark_failed(session: AsyncSession, import_id: int, error: str) -> None:
    imp = await session.get(YoutubeImport, import_id)
    if imp is not None:
        imp.status = "failed"
        imp.last_error = error[:512]
        await session.commit()

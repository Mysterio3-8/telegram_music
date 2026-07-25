"""Добавление трека по свободному запросу пользователя.

Находим лучшее совпадение во всех источниках и загружаем из того, где нашли:
SoundCloud отдаёт чистое аудио как есть, YouTube — с приведением к mp3.
"""
import asyncio
import logging

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Track
from app.services.soundcloud import download_soundcloud_audio
from app.services.track_lookup.providers import SOURCE_SOUNDCLOUD
from app.services.track_lookup.ranking import Candidate
from app.services.youtube.downloader import DownloadedAudio, download_audio
from app.services.youtube.user_import import (
    UserImportRejected,
    extract_video_id,
    import_downloaded_audio,
)
from app.services.track_lookup import find_track

logger = logging.getLogger(__name__)

NOT_FOUND_MESSAGE = (
    "Не нашли такой трек. Уточните исполнителя и название — например «Kizaru Фейк Айди»."
)


def download_candidate(candidate: Candidate) -> DownloadedAudio | None:
    """Загружает найденный трек из его источника."""
    if candidate.source == SOURCE_SOUNDCLOUD:
        result = download_soundcloud_audio(candidate.url)
        return result[0] if result else None
    video_id = extract_video_id(candidate.url)
    return download_audio(video_id, as_mp3=True) if video_id else None


async def import_by_query(
    session: AsyncSession, bot: Bot, query: str, telegram_id: int
) -> tuple[Track, bool]:
    """Находит трек по запросу и добавляет пользователю. Возвращает (трек, создан_ли)."""
    candidate = await asyncio.to_thread(find_track, query)
    if candidate is None:
        raise UserImportRejected(NOT_FOUND_MESSAGE)

    audio = await asyncio.to_thread(download_candidate, candidate)
    if audio is None:
        raise UserImportRejected(NOT_FOUND_MESSAGE)

    track, created = await import_downloaded_audio(session, bot, audio, telegram_id)
    logger.info(
        "Импорт по запросу «%s» источник=%s user=%s → track=%s (created=%s)",
        query, candidate.source, telegram_id, track.id, created,
    )
    return track, created

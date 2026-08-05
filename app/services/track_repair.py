"""Восстановление трека, потерявшего файл в Telegram.

`tg_file_id` принадлежит боту, который загрузил файл: после переезда на нового
бота все старые идентификаторы становятся чужими, и Telegram отвечает «wrong
file identifier». Архивных копий у каталога нет (`storage_path` пуст), поэтому
единственный источник байтов — открытые источники: находим трек заново по
«Исполнитель — Название» и минтим в архивный чат, обновляя ту же строку в базе.

Побочно это лечит любую будущую смену токена и битые file_id.
"""
import asyncio
import logging

from aiogram import Bot
from aiogram.types import BufferedInputFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import Track
from app.services.track_lookup import find_track
from app.services.track_lookup.importer import download_candidate
from app.services.track_meta import build_filename, retag_audio

logger = logging.getLogger(__name__)


async def repair_track_file_id(session: AsyncSession, bot: Bot, track: Track) -> bool:
    """Заново скачивает трек из источника и минтит file_id текущего бота.

    True — file_id обновлён. False — трек в источниках не нашёлся, строку не
    трогаем: пусть остаётся в библиотеке, вдруг найдётся позже.
    """
    query = f"{track.artist} {track.title}".strip()
    candidate = await asyncio.to_thread(find_track, query)
    if candidate is None:
        logger.warning("Восстановление track=%s: «%s» не нашлось", track.id, query)
        return False

    audio = await asyncio.to_thread(download_candidate, candidate)
    if audio is None:
        logger.warning("Восстановление track=%s: не скачалось", track.id)
        return False

    tagged = retag_audio(audio.data, track.format, track.title, track.artist)
    sent = await bot.send_audio(
        settings.effective_archive_chat_id,
        BufferedInputFile(tagged, filename=build_filename(track.artist, track.title, track.format)),
        title=track.title,
        performer=track.artist,
        duration=track.duration or None,
    )
    if sent.audio is None:
        return False

    track.tg_file_id = sent.audio.file_id
    track.meta_synced = True
    await session.commit()
    logger.info("Восстановлен track=%s", track.id)
    return True

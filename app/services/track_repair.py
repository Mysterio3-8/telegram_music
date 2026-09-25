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
from app.services.track_lookup.importer import download_with_fallback
from app.services.track_meta import build_filename, retag_audio

logger = logging.getLogger(__name__)

# Неудачное восстановление помним 10 минут. Живой прогон 25.09: воркер сдавался
# за 1.6 сек, а API ещё 25 сек ждал file_id, которого не будет, — всё это время
# плеер стоял на 0:00. С пометкой API отвечает отказом сразу, и плеер идёт
# дальше; повторные нажатия на тот же мёртвый трек не гоняют воркер впустую.
FAILED_TTL_SECONDS = 600
_FAILED_PREFIX = "repair:failed:"


def _redis():
    from app.services.prefetch import _redis as shared

    return shared()


def mark_failed(track_id: int, ttl: int = FAILED_TTL_SECONDS) -> None:
    client = _redis()
    if client is None:
        return
    try:
        client.set(f"{_FAILED_PREFIX}{track_id}", "1", ex=ttl)
    except Exception:  # noqa: BLE001 — пометка лишь ускоряет отказ
        logger.warning("Пометка неудачного восстановления не записалась", exc_info=True)


def recently_failed(track_id: int) -> bool:
    client = _redis()
    if client is None:
        return False
    try:
        return bool(client.exists(f"{_FAILED_PREFIX}{track_id}"))
    except Exception:  # noqa: BLE001
        return False


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

    # С перебором замен: у мейджоров оригинал часто под DRM или превью Go+,
    # а рядом лежит качающаяся копия той же записи (живой прогон 25.09: DIOR
    # сдавался за 1.6 сек, не попробовав ни одной замены)
    audio = await asyncio.to_thread(download_with_fallback, candidate)
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

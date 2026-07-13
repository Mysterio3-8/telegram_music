"""Отдача байтов трека для Mini App-плеера.

Доступ — по HMAC-подписи с истечением (build_audio_url), не по JWT: <audio src>
не умеет слать заголовки. Range поддержан вручную — без него в Safari/Chrome
не работает перемотка.
"""
import io
import logging

from aiogram import Bot
from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.api.security import verify_audio_signature
from app.config import settings
from app.db.base import session_factory
from app.db.models import Track
from app.services.library import get_track

logger = logging.getLogger(__name__)

router = APIRouter(tags=["audio"])

_MEDIA_TYPES = {
    "mp3": "audio/mpeg",
    "flac": "audio/flac",
    "wav": "audio/wav",
    "m4a": "audio/mp4",
    "ogg": "audio/ogg",
}


def _media_type(track: Track) -> str:
    return _MEDIA_TYPES.get((track.format or "mp3").lower(), "audio/mpeg")


async def _load_track_bytes(track: Track) -> bytes | None:
    """Байты трека: архивное хранилище, иначе скачивание из Telegram (getFile ≤ 20 МБ)."""
    if track.storage_path:
        try:
            from app.storage import get_storage

            storage = get_storage()
            return await run_in_threadpool(storage.load, f"tracks/{track.id}")
        except Exception:  # noqa: BLE001
            logger.warning("Архив недоступен track=%s", track.id, exc_info=True)
    if track.tg_file_id:
        try:
            bot = Bot(token=settings.bot_token)
            try:
                buffer = io.BytesIO()
                await bot.download(track.tg_file_id, destination=buffer)
                return buffer.getvalue()
            finally:
                await bot.session.close()
        except Exception:  # noqa: BLE001
            logger.warning("Не удалось скачать track=%s из Telegram", track.id, exc_info=True)
    return None


def _range_response(data: bytes, range_header: str, media_type: str) -> Response:
    """Единственный диапазон bytes=start-end поверх байтов в памяти (файлы ≤ 50 МБ)."""
    try:
        unit, _, spec = range_header.partition("=")
        if unit.strip() != "bytes" or "," in spec:
            raise ValueError
        start_raw, _, end_raw = spec.partition("-")
        start = int(start_raw) if start_raw else 0
        end = int(end_raw) if end_raw else len(data) - 1
    except ValueError:
        raise HTTPException(status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE, "Некорректный Range")

    end = min(end, len(data) - 1)
    if start > end or start >= len(data):
        raise HTTPException(status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE, "Range вне файла")

    chunk = data[start : end + 1]
    return Response(
        content=chunk,
        status_code=status.HTTP_206_PARTIAL_CONTENT,
        media_type=media_type,
        headers={
            "Content-Range": f"bytes {start}-{end}/{len(data)}",
            "Accept-Ranges": "bytes",
            "Cache-Control": "private, max-age=3600",
        },
    )


@router.get("/tracks/{track_id}/audio")
async def stream_track_audio(
    track_id: int,
    request: Request,
    exp: int = Query(...),
    sig: str = Query(...),
) -> Response:
    if not verify_audio_signature(track_id, exp, sig):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Ссылка недействительна или истекла")

    # Без DI-цепочки get_db/JWT: запрос уже авторизован подписью
    async with session_factory() as session:
        track = await get_track(session, track_id)
    if track is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Трек не найден")

    data = await _load_track_bytes(track)
    if data is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Файл трека недоступен")

    media_type = _media_type(track)
    range_header = request.headers.get("range")
    if range_header:
        return _range_response(data, range_header, media_type)
    return Response(
        content=data,
        media_type=media_type,
        headers={"Accept-Ranges": "bytes", "Cache-Control": "private, max-age=3600"},
    )

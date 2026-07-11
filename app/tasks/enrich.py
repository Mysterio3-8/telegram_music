import asyncio
import io
import logging

from aiogram import Bot
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.db.models import Track
from app.services.fingerprint import compute_fingerprint_from_bytes
from app.storage import get_storage
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


async def _download_bytes(file_id: str) -> bytes:
    bot = Bot(token=settings.bot_token)
    try:
        buffer = io.BytesIO()
        await bot.download(file_id, destination=buffer)
        return buffer.getvalue()
    finally:
        await bot.session.close()


async def _apply_enrichment(track_id: int, fingerprint: str | None, storage_path: str) -> None:
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            track = await session.get(Track, track_id)
            if track is None:
                return
            if fingerprint:
                track.fingerprint = fingerprint
            track.storage_path = storage_path
            await session.commit()
    finally:
        await engine.dispose()


@celery_app.task(name="enrich_track")
def enrich_track(track_id: int, file_id: str) -> None:
    """Скачивает файл из Telegram, считает отпечаток, кладёт в архивное хранилище."""
    data = asyncio.run(_download_bytes(file_id))
    fingerprint = compute_fingerprint_from_bytes(data)
    storage_path = get_storage().save(f"tracks/{track_id}", data)
    asyncio.run(_apply_enrichment(track_id, fingerprint, storage_path))
    logger.info(
        "Трек обогащён track=%s fingerprint=%s path=%s",
        track_id,
        "yes" if fingerprint else "no",
        storage_path,
    )

"""Celery-задача переноса плейлиста: долгая работа с сетью — не в хендлере бота."""
import asyncio
import logging

from aiogram import Bot
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.services.playlist_transfer.parsers import TransferItem
from app.services.playlist_transfer.service import transfer_playlist
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


async def _run(items: list[dict], telegram_id: int) -> None:
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    bot = Bot(token=settings.bot_token)
    try:
        parsed = [TransferItem(i["artist"], i["title"]) for i in items]
        async with factory() as session:
            report = await transfer_playlist(session, bot, parsed, telegram_id)
        await bot.send_message(telegram_id, f"📥 Перенос завершён\n\n{report.summary()}")
    except Exception:  # noqa: BLE001
        logger.exception("Перенос плейлиста упал user=%s", telegram_id)
        try:
            await bot.send_message(telegram_id, "Перенос не удался — попробуйте позже.")
        except Exception:  # noqa: BLE001
            pass
    finally:
        await bot.session.close()
        await engine.dispose()


@celery_app.task(name="transfer.playlist", bind=True, max_retries=0)
def transfer_playlist_task(self, items: list[dict], telegram_id: int) -> None:  # noqa: ARG001
    asyncio.run(_run(items, telegram_id))

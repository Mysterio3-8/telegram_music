"""Фоновые задачи импорта из личного Telegram-канала — без файлов на диске.

Отдельная очередь `telegram_channel`. Автоповтор с растущей задержкой.
on_failure помечает задачу failed — один проблемный пост не останавливает очередь.
"""
import asyncio
import logging

from aiogram import Bot
from celery import Task
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.services.app_settings import is_telegram_channel_enabled
from app.services.telegram_channel.client import build_client, is_configured
from app.services.telegram_channel.importer import mark_failed, process_import
from app.services.telegram_channel.sources import (
    get_source,
    pending_import_ids,
    register_found_messages,
    requeue_stuck,
    sources_due_for_check,
)
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def _engine_and_factory():
    engine = create_async_engine(settings.database_url)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


async def _with_session(coro):
    engine, factory = _engine_and_factory()
    try:
        async with factory() as session:
            return await coro(session)
    finally:
        await engine.dispose()


class _ImportTask(Task):
    def on_failure(self, exc, task_id, args, kwargs, einfo) -> None:
        import_id = kwargs.get("import_id") or (args[0] if args else None)
        if import_id is not None:
            asyncio.run(_with_session(lambda s: mark_failed(s, import_id, str(exc))))


@celery_app.task(
    base=_ImportTask,
    name="telegram_channel.process_import",
    autoretry_for=(Exception,),
    retry_backoff=30,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=settings.telegram_channel_max_retries,
)
def telegram_channel_process_import(import_id: int) -> None:
    async def _run(session):
        if not await is_telegram_channel_enabled(session):
            logger.info("Импорт из Telegram-канала выключен — задача %s пропущена", import_id)
            return
        if not is_configured():
            logger.warning("TELEGRAM_API_ID/TELEGRAM_API_HASH не заданы — задача %s пропущена", import_id)
            return
        bot = Bot(token=settings.bot_token)
        try:
            async with build_client() as client:
                await process_import(session, bot, client, import_id)
        finally:
            await bot.session.close()

    asyncio.run(_with_session(_run))


@celery_app.task(name="telegram_channel.scan_source")
def telegram_channel_scan_source(source_id: int) -> None:
    async def _scan(session) -> list[int]:
        if not await is_telegram_channel_enabled(session):
            logger.info("Импорт из Telegram-канала выключен — скан источника %s пропущен", source_id)
            return []
        if not is_configured():
            logger.warning("TELEGRAM_API_ID/TELEGRAM_API_HASH не заданы — скан пропущен")
            return []
        source = await get_source(session, source_id)
        if source is None or source.status != "active":
            return []
        from app.services.telegram_channel.scanner import list_audio_messages

        async with build_client() as client:
            refs = await list_audio_messages(client, source.channel, source.last_message_id)
        await register_found_messages(session, source_id, refs)
        return await pending_import_ids(session, source_id)

    ids = asyncio.run(_with_session(_scan))
    for import_id in ids:
        telegram_channel_process_import.delay(import_id=import_id)
    logger.info(
        "Telegram-канал scan source=%s: в очередь поставлено %s задач", source_id, len(ids)
    )


@celery_app.task(name="telegram_channel.recover")
def telegram_channel_recover() -> None:
    """Возвращает оборванные задачи в очередь после аварийного завершения."""
    async def _recover(session) -> list[int]:
        from sqlalchemy import select

        from app.db.models import TelegramChannelImport

        await requeue_stuck(session)
        stmt = select(TelegramChannelImport.id).where(TelegramChannelImport.status == "pending")
        return list((await session.scalars(stmt)).all())

    ids = asyncio.run(_with_session(_recover))
    for import_id in ids:
        telegram_channel_process_import.delay(import_id=import_id)
    logger.info("Telegram-канал recover: переочерёдно %s задач", len(ids))


@celery_app.task(name="telegram_channel.scan_due")
def telegram_channel_scan_due() -> None:
    """Периодическая проверка источников старше интервала."""
    ids = asyncio.run(_with_session(sources_due_for_check))
    for source_id in ids:
        telegram_channel_scan_source.delay(source_id=source_id)
    logger.info("Telegram-канал scan_due: запущена проверка %s источников", len(ids))

"""Фоновые задачи YouTube-импорта (доп. ТЗ, §12-§15).

Отдельная очередь `youtube` — обрабатывается воркером с ограниченной параллельностью
(§14). Автоповтор с растущей задержкой (§13). on_failure помечает задачу failed —
один проблемный трек не останавливает очередь.
"""
import asyncio
import logging

from celery import Task
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.services.app_settings import is_youtube_enabled
from app.services.youtube.importer import mark_failed, process_import
from app.services.youtube.sources import (
    get_source,
    pending_import_ids,
    register_found_videos,
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
    name="youtube.process_import",
    autoretry_for=(Exception,),
    retry_backoff=30,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=settings.youtube_max_retries,
)
def youtube_process_import(import_id: int) -> None:
    async def _run(session):
        if not await is_youtube_enabled(session):
            logger.info("YouTube-импортёр выключен — задача %s пропущена", import_id)
            return
        return await process_import(session, import_id)

    asyncio.run(_with_session(_run))


@celery_app.task(name="youtube.scan_source")
def youtube_scan_source(source_id: int) -> None:
    async def _scan(session) -> list[int]:
        if not await is_youtube_enabled(session):
            logger.info("YouTube-импортёр выключен — скан источника %s пропущен", source_id)
            return []
        source = await get_source(session, source_id)
        if source is None or source.status != "active":
            return []
        from app.services.youtube.downloader import list_videos

        videos = list_videos(source.url)
        await register_found_videos(session, source_id, videos)
        return await pending_import_ids(session, source_id)

    ids = asyncio.run(_with_session(_scan))
    for import_id in ids:
        youtube_process_import.delay(import_id=import_id)
    logger.info("YouTube scan source=%s: в очередь поставлено %s задач", source_id, len(ids))


@celery_app.task(name="youtube.recover")
def youtube_recover() -> None:
    """Возвращает оборванные задачи в очередь и добивает pending (§15)."""
    async def _recover(session) -> list[int]:
        from sqlalchemy import select

        from app.db.models import YoutubeImport

        await requeue_stuck(session)
        stmt = select(YoutubeImport.id).where(YoutubeImport.status == "pending")
        return list((await session.scalars(stmt)).all())

    ids = asyncio.run(_with_session(_recover))
    for import_id in ids:
        youtube_process_import.delay(import_id=import_id)
    logger.info("YouTube recover: переочерёдно %s задач", len(ids))


@celery_app.task(name="youtube.scan_due")
def youtube_scan_due() -> None:
    """Периодическая проверка источников старше интервала (§11)."""
    ids = asyncio.run(_with_session(sources_due_for_check))
    for source_id in ids:
        youtube_scan_source.delay(source_id=source_id)
    logger.info("YouTube scan_due: запущена проверка %s источников", len(ids))

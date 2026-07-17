"""Фоновые задачи YouTube-импорта (доп. ТЗ, §12-§15).

Отдельная очередь `youtube` — обрабатывается воркером с ограниченной параллельностью
(§14). Автоповтор с растущей задержкой (§13). on_failure помечает задачу failed —
один проблемный трек не останавливает очередь.
"""
import asyncio
import logging

from aiogram import Bot
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
        bot = Bot(token=settings.bot_token)
        try:
            return await process_import(session, bot, import_id)
        finally:
            await bot.session.close()

    asyncio.run(_with_session(_run))


@celery_app.task(name="youtube.user_import", bind=True, max_retries=2)
def youtube_user_import(
    self, video_id: str, telegram_id: int, chat_id: int, quiet: bool = False
) -> None:
    """Импорт по ссылке от пользователя: скачивает, заводит трек, присылает его в чат.
    quiet — пачечный режим (плейлист): треки тихо падают в библиотеку, без сообщений."""
    from app.services.youtube.user_import import UserImportRejected, process_user_import

    async def _run(session):
        bot = Bot(token=settings.bot_token)
        try:
            try:
                track, created = await process_user_import(session, bot, video_id, telegram_id)
            except UserImportRejected as exc:
                if not quiet:
                    await bot.send_message(chat_id, f"❌ Не добавили: {exc}")
                return
            if quiet:
                return
            note = "добавлен в общую базу и вашу библиотеку" if created else "уже был в базе — добавили в вашу библиотеку"
            if track.tg_file_id:
                await bot.send_audio(
                    chat_id,
                    track.tg_file_id,
                    caption=f"✅ {track.artist} — {track.title}\nТрек {note}.",
                )
            else:
                await bot.send_message(chat_id, f"✅ {track.artist} — {track.title} — {note}.")
        finally:
            await bot.session.close()

    try:
        asyncio.run(_with_session(_run))
    except Exception as exc:  # noqa: BLE001 — повторяем с паузой; после 2 попыток сообщаем
        if self.request.retries >= self.max_retries:
            if not quiet:
                asyncio.run(
                    _notify(chat_id, "❌ Не удалось скачать трек по ссылке. Попробуйте позже.")
                )
            logger.warning("User-импорт %s не удался: %s", video_id, exc)
            return
        raise self.retry(exc=exc, countdown=60)


async def _notify(chat_id: int, text: str) -> None:
    bot = Bot(token=settings.bot_token)
    try:
        await bot.send_message(chat_id, text)
    finally:
        await bot.session.close()


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


def _first_admin_id() -> int | None:
    admins = sorted(settings.admin_id_set)
    return admins[0] if admins else None


@celery_app.task(name="youtube.soundcloud_scan_source", bind=True, max_retries=1)
def soundcloud_scan_source(self, source_id: int, chat_id: int | None = None) -> None:
    """Скан одного SoundCloud-источника: дедуп делает импорт инкрементальным —
    забираются только новые биты. chat_id задан (ручной запуск из админки) —
    отчёт всегда; автоскан молчит, если ничего нового, и пишет первому админу,
    когда появились новые минусы.
    """
    from app.db.models import SoundcloudSource
    from app.services.soundcloud_import import import_soundcloud_minuses
    from app.services.soundcloud_sources import mark_checked

    async def _run(session):
        source = await session.get(SoundcloudSource, source_id)
        if source is None or source.status != "active":
            return
        bot = Bot(token=settings.bot_token)
        try:
            report = await import_soundcloud_minuses(session, bot, source.url)
            await mark_checked(session, source_id, report.found, report.imported)
            notify_chat = chat_id or (_first_admin_id() if report.imported else None)
            if notify_chat:
                await bot.send_message(
                    notify_chat,
                    f"🎼 SoundCloud-скан {source.url}\n\n{report.summary()}\n\n"
                    "Источник сохранён — новые биты будут подтягиваться автоматически.",
                )
        finally:
            await bot.session.close()

    try:
        asyncio.run(_with_session(_run))
    except Exception as exc:  # noqa: BLE001 — одна повторная попытка, потом отчёт об ошибке
        if self.request.retries >= self.max_retries:
            if chat_id:
                asyncio.run(_notify(chat_id, "❌ SoundCloud-импорт не удался. Попробуйте позже."))
            logger.warning("SoundCloud-скан source=%s не удался: %s", source_id, exc)
            return
        raise self.retry(exc=exc, countdown=120)


@celery_app.task(name="youtube.soundcloud_scan_due")
def soundcloud_scan_due() -> None:
    """Периодическая проверка SoundCloud-источников (владелец публикует новые биты часто)."""
    from app.services.soundcloud_sources import sources_due_for_check as sc_due

    ids = asyncio.run(_with_session(sc_due))
    for source_id in ids:
        soundcloud_scan_source.delay(source_id=source_id)
    logger.info("SoundCloud scan_due: запущена проверка %s источников", len(ids))

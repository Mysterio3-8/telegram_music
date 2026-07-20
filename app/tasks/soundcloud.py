"""Фоновые задачи SoundCloud-импорта (запрос владельца: автопополнение треков).

Отдельная очередь `soundcloud` — намеренно НЕ шарит воркер с `youtube`: там
бэклог из сотен поштучных импортов конкретных видео, и SoundCloud-скан,
попав в общую очередь, стоял бы в хвосте и выглядел «зависшим». Здесь свой
воркер с concurrency=1 (анти-бан — никаких параллельных запросов к SoundCloud).
"""
import asyncio
import logging

from aiogram import Bot
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
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


async def _notify(chat_id: int, text: str) -> None:
    bot = Bot(token=settings.bot_token)
    try:
        await bot.send_message(chat_id, text)
    finally:
        await bot.session.close()


def _first_admin_id() -> int | None:
    admins = sorted(settings.admin_id_set)
    return admins[0] if admins else None


@celery_app.task(name="soundcloud.scan_source", bind=True, max_retries=1)
def soundcloud_scan_source(self, source_id: int, chat_id: int | None = None) -> None:
    """Скан одного SoundCloud-источника: дедуп делает импорт инкрементальным —
    забираются только новые треки. chat_id задан (ручной запуск из админки) —
    отчёт всегда; автоскан молчит, если ничего нового, и пишет первому админу,
    когда появились новые треки.
    """
    from app.db.models import SoundcloudSource
    from app.services.soundcloud_import import import_soundcloud_tracks
    from app.services.soundcloud_sources import mark_checked

    async def _run(session):
        source = await session.get(SoundcloudSource, source_id)
        if source is None or source.status != "active":
            return
        bot = Bot(token=settings.bot_token)
        try:
            report = await import_soundcloud_tracks(session, bot, source.url)
            await mark_checked(session, source_id, report.found, report.imported)
            notify_chat = chat_id or (_first_admin_id() if report.imported else None)
            if notify_chat:
                await bot.send_message(
                    notify_chat,
                    f"🎧 SoundCloud-скан {source.url}\n\n{report.summary()}\n\n"
                    "Источник сохранён — новые треки будут подтягиваться автоматически.",
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


@celery_app.task(name="soundcloud.scan_due")
def soundcloud_scan_due() -> None:
    """Периодическая проверка SoundCloud-источников (владелец публикует новые биты часто)."""
    from app.services.soundcloud_sources import sources_due_for_check

    ids = asyncio.run(_with_session(sources_due_for_check))
    for source_id in ids:
        soundcloud_scan_source.delay(source_id=source_id)
    logger.info("SoundCloud scan_due: запущена проверка %s источников", len(ids))


@celery_app.task(name="soundcloud.user_import", bind=True, max_retries=2)
def soundcloud_user_import(
    self, url: str, telegram_id: int, chat_id: int, quiet: bool = False
) -> None:
    """Импорт одного трека SoundCloud по ссылке от пользователя: скачивает, заводит
    трек, присылает его в чат. quiet — пачечный режим (профиль/лайки): треки тихо
    падают в библиотеку без сообщений на каждый."""
    from app.services.soundcloud_import import process_user_soundcloud_import
    from app.services.youtube.user_import import UserImportRejected

    async def _run(session):
        bot = Bot(token=settings.bot_token)
        try:
            try:
                track, created = await process_user_soundcloud_import(
                    session, bot, url, telegram_id
                )
            except UserImportRejected as exc:
                if not quiet:
                    await bot.send_message(chat_id, f"❌ Не добавили: {exc}")
                return
            if quiet:
                return
            note = (
                "добавлен в общую базу и вашу библиотеку"
                if created
                else "уже был в базе — добавили в вашу библиотеку"
            )
            if track.tg_file_id:
                await bot.send_audio(
                    chat_id, track.tg_file_id, caption=f"✅ {track.artist} — {track.title}\nТрек {note}."
                )
            else:
                await bot.send_message(chat_id, f"✅ {track.artist} — {track.title} — {note}.")
        finally:
            await bot.session.close()

    try:
        asyncio.run(_with_session(_run))
    except Exception as exc:  # noqa: BLE001 — повтор с паузой; после ретраев сообщаем
        if self.request.retries >= self.max_retries:
            if not quiet:
                asyncio.run(_notify(chat_id, "❌ Не удалось скачать трек по ссылке. Попробуйте позже."))
            logger.warning("SoundCloud user-импорт %s не удался: %s", url, exc)
            return
        raise self.retry(exc=exc, countdown=60)

"""Задача импорта по ссылке с произвольной площадки (Bandcamp, VK, Mixcloud…).

Живёт в очереди `youtube_user` рядом с остальными поштучными импортами: ответа
ждёт живой человек, и стоять за массовым сканом чьего-то профиля она не должна.

Скачивание в воркере, а не в боте, по той же причине, что и везде: ffmpeg на
боксе 961 МБ дважды ронял прод по OOM.
"""
import asyncio
import logging

from aiogram import Bot

from app.config import settings
from app.db.base import build_task_engine
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


async def _with_session(coro):
    engine, factory = build_task_engine()
    try:
        async with factory() as session:
            return await coro(session)
    finally:
        await engine.dispose()


@celery_app.task(name="link.user_import", bind=True, max_retries=2, queue="youtube_user")
def link_user_import(
    self, url: str, telegram_id: int, chat_id: int, quiet: bool = False
) -> None:
    """Один трек по ссылке. quiet — пачечный режим (плейлист/профиль): треки
    тихо падают в библиотеку, без сообщения на каждый."""
    from app.services.link_import import process_user_link_import
    from app.services.youtube.user_import import UserImportRejected

    async def _run(session):
        bot = Bot(token=settings.bot_token)
        try:
            try:
                track, created = await process_user_link_import(
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
            caption = f"✅ {track.artist} — {track.title}"
            if track.tg_file_id:
                await bot.send_audio(chat_id, track.tg_file_id, caption=f"{caption}\nТрек {note}.")
            else:
                await bot.send_message(chat_id, f"{caption} — {note}.")
        finally:
            await bot.session.close()

    try:
        asyncio.run(_with_session(_run))
    except Exception as exc:  # noqa: BLE001 — повтор с паузой; после ретраев сообщаем
        if self.request.retries >= self.max_retries:
            logger.warning("Импорт по ссылке %s не удался: %s", url, exc)
            return
        raise self.retry(exc=exc, countdown=60)

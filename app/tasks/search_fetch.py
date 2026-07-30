"""Фоновая задача спрятанного поискового парсера #2 (решение владельца).

Находит трек отовсюду по свободному запросу и присылает пользователю в чат.
Живёт в очереди `youtube_user` (рядом с поштучными импортами по ссылке) — не
делит воркер с массовым SoundCloud-сканом.
"""
import asyncio
import logging

from aiogram import Bot

from app.config import settings
from app.db.base import build_task_engine
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def _engine_and_factory():
    return build_task_engine()


async def _with_session(coro):
    engine, factory = _engine_and_factory()
    try:
        async with factory() as session:
            return await coro(session)
    finally:
        await engine.dispose()


@celery_app.task(name="search.fetch", bind=True, max_retries=2, queue="youtube_user")
def search_fetch(self, query: str, telegram_id: int, chat_id: int, quiet: bool = False) -> None:
    """Ищет трек по запросу отовсюду, минтит и присылает в чат. quiet — без
    сообщения о неудаче (например, авто-дозагрузка по промаху поиска в Mini App)."""
    from app.services.track_lookup.importer import import_by_query
    from app.services.youtube.user_import import UserImportRejected

    async def _run(session):
        bot = Bot(token=settings.bot_token)
        try:
            try:
                track, _ = await import_by_query(session, bot, query, telegram_id)
            except UserImportRejected:
                if not quiet:
                    await bot.send_message(chat_id, f"❌ Не нашли «{query}». Попробуйте иначе.")
                return
            if quiet:
                return
            if track.tg_file_id:
                await bot.send_audio(
                    chat_id, track.tg_file_id,
                    caption=f"✅ {track.artist} — {track.title}\nНашли и добавили в вашу библиотеку.",
                )
            else:
                await bot.send_message(chat_id, f"✅ {track.artist} — {track.title} — добавлен.")
        finally:
            await bot.session.close()

    try:
        asyncio.run(_with_session(_run))
    except Exception as exc:  # noqa: BLE001 — повтор с паузой; после ретраев сообщаем
        if self.request.retries >= self.max_retries:
            logger.warning("Поисковый парсер «%s» не удался: %s", query, exc)
            return
        raise self.retry(exc=exc, countdown=60)

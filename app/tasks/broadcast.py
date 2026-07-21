"""Celery-задача рассылки: отправка всем пользователям с троттлингом.

Троттлинг ~25 msg/sec (лимит Telegram — 30/sec). Заблокировавшие бота
помечаются users.bot_blocked и выпадают из будущих рассылок. По завершении
админу приходит отчёт: доставлено / заблокировали / ошибок.
"""
import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.services.broadcast import MESSAGES_PER_SECOND, active_recipient_ids, mark_bot_blocked
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


async def _send_one(bot: Bot, chat_id: int, text: str, photo_file_id: str | None) -> None:
    if photo_file_id:
        await bot.send_photo(chat_id, photo_file_id, caption=text or None)
    else:
        await bot.send_message(chat_id, text)


async def _run_broadcast(text: str, photo_file_id: str | None, admin_chat_id: int) -> None:
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    bot = Bot(token=settings.bot_token)
    delivered = blocked = failed = 0
    try:
        async with factory() as session:
            recipients = await active_recipient_ids(session)
        for chat_id in recipients:
            try:
                await _send_one(bot, chat_id, text, photo_file_id)
                delivered += 1
            except TelegramRetryAfter as exc:
                # Telegram просит притормозить — ждём и повторяем один раз
                await asyncio.sleep(exc.retry_after + 1)
                try:
                    await _send_one(bot, chat_id, text, photo_file_id)
                    delivered += 1
                except Exception:  # noqa: BLE001
                    failed += 1
            except TelegramForbiddenError:
                blocked += 1
                async with factory() as session:
                    await mark_bot_blocked(session, chat_id)
            except Exception:  # noqa: BLE001
                failed += 1
                logger.warning("Рассылка: не доставлено chat=%s", chat_id, exc_info=True)
            await asyncio.sleep(1 / MESSAGES_PER_SECOND)

        report = (
            "📣 Рассылка завершена\n\n"
            f"✅ Доставлено: {delivered}\n"
            f"🚫 Заблокировали бота: {blocked}\n"
            f"❌ Ошибок: {failed}"
        )
        try:
            await bot.send_message(admin_chat_id, report)
        except Exception:  # noqa: BLE001
            logger.warning("Рассылка: не удалось отправить отчёт админу", exc_info=True)
        logger.info("Рассылка: delivered=%s blocked=%s failed=%s", delivered, blocked, failed)
    finally:
        await bot.session.close()
        await engine.dispose()


@celery_app.task(name="broadcast.send")
def send_broadcast(text: str, photo_file_id: str | None, admin_chat_id: int) -> None:
    asyncio.run(_run_broadcast(text, photo_file_id, admin_chat_id))

"""Рассылка админа всем пользователям (NEXT_SESSION P6).

Сервис знает только о БД: выборка получателей и отметка «бот заблокирован».
Сама отправка с троттлингом — в Celery-задаче (app/tasks/broadcast.py).
"""
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User

# Telegram даёт ~30 сообщений/сек на бота; держим запас
MESSAGES_PER_SECOND = 25


async def active_recipient_ids(session: AsyncSession) -> list[int]:
    """telegram_id всех, кто не блокировал бота."""
    rows = await session.scalars(
        select(User.telegram_id).where(User.bot_blocked.is_(False)).order_by(User.id)
    )
    return list(rows)


async def mark_bot_blocked(session: AsyncSession, telegram_id: int) -> None:
    """Пользователь заблокировал бота — исключаем из будущих рассылок (и статистики)."""
    await session.execute(
        update(User).where(User.telegram_id == telegram_id).values(bot_blocked=True)
    )
    await session.commit()

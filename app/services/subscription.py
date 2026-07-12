"""Обязательная подписка на каналы (TZ §14-17): проверка через getChatMember с TTL-кэшем.

Бот обязан быть администратором проверяемых каналов — иначе Telegram не гарантирует
корректный ответ getChatMember для чужих участников.
"""
import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramAPIError
from aiogram.types import ChatMemberRestricted
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import SubscriptionStatus
from app.services.users import is_admin

logger = logging.getLogger(__name__)

_SUBSCRIBED_STATUSES = {
    ChatMemberStatus.MEMBER,
    ChatMemberStatus.ADMINISTRATOR,
    ChatMemberStatus.CREATOR,
}


async def check_channel_membership(bot: Bot, telegram_id: int, channel: str) -> bool:
    """Живой запрос к Telegram. Ошибка API → считаем неподписанным (fail-closed)."""
    try:
        member = await bot.get_chat_member(chat_id=channel, user_id=telegram_id)
    except TelegramAPIError:
        logger.warning("getChatMember недоступен channel=%s user=%s", channel, telegram_id, exc_info=True)
        return False
    if member.status in _SUBSCRIBED_STATUSES:
        return True
    if isinstance(member, ChatMemberRestricted):
        return member.is_member
    return False


async def _get_cached(session: AsyncSession, user_id: int, channel: str) -> SubscriptionStatus | None:
    return await session.get(SubscriptionStatus, (user_id, channel))


async def _store(session: AsyncSession, user_id: int, channel: str, is_subscribed: bool) -> None:
    row = await _get_cached(session, user_id, channel)
    if row is None:
        row = SubscriptionStatus(user_id=user_id, channel=channel)
        session.add(row)
    row.is_subscribed = is_subscribed
    row.checked_at = datetime.now(timezone.utc)
    await session.commit()


async def is_channel_subscribed(
    session: AsyncSession,
    bot: Bot,
    user_id: int,
    telegram_id: int,
    channel: str,
    force: bool = False,
) -> bool:
    """Кэшированная (TTL) или свежая проверка одного канала."""
    if not force:
        cached = await _get_cached(session, user_id, channel)
        if cached is not None:
            ttl = timedelta(minutes=settings.subscription_cache_ttl_minutes)
            checked_at = cached.checked_at
            if checked_at.tzinfo is None:
                checked_at = checked_at.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) - checked_at < ttl:
                return cached.is_subscribed

    is_subscribed = await check_channel_membership(bot, telegram_id, channel)
    await _store(session, user_id, channel, is_subscribed)
    return is_subscribed


async def is_fully_subscribed(
    session: AsyncSession,
    bot: Bot,
    user_id: int,
    telegram_id: int,
    force: bool = False,
) -> bool:
    """True — подписан на все обязательные каналы (или админ с включённым байпасом)."""
    if settings.admin_bypass_subscription and is_admin(telegram_id):
        return True
    for channel, _label in settings.required_channels:
        if not await is_channel_subscribed(session, bot, user_id, telegram_id, channel, force):
            return False
    return True

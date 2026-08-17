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


async def check_channel_membership(bot: Bot, telegram_id: int, channel: str) -> bool | None:
    """Живой запрос к Telegram. True/False — ответ Telegram, None — спросить не удалось.

    ⚠️ None и False — РАЗНОЕ. «Не подписан» это факт, а сетевой сбой, 429 или
    500 у Telegram — отсутствие ответа. Раньше и то и другое было False, и этот
    False попадал в кэш на весь TTL: подписанный человек оказывался заперт во
    всём боте до истечения кэша, ничего при этом не сделав. На проде за 7 дней
    таких сбоев не было ни одного, но цена срабатывания слишком велика.

    Для НЕМЕДЛЕННОГО решения None по-прежнему означает «не пускаем» (fail-closed
    остаётся), разница только в том, что несостоявшийся ответ не запоминается.
    """
    try:
        member = await bot.get_chat_member(chat_id=channel, user_id=telegram_id)
    except TelegramAPIError:
        logger.warning("getChatMember недоступен channel=%s user=%s", channel, telegram_id, exc_info=True)
        return None
    if member.status in _SUBSCRIBED_STATUSES:
        return True
    if isinstance(member, ChatMemberRestricted):
        return member.is_member
    return False


async def is_bot_admin_of_channel(bot: Bot, channel: str) -> bool:
    """True — бот является администратором канала. Только это и нужно, чтобы гейт
    мог проверять подписчиков; подписка самого владельца-админа НЕ требуется."""
    try:
        me = await bot.get_me()
        member = await bot.get_chat_member(chat_id=channel, user_id=me.id)
    except TelegramAPIError:
        logger.warning("не удалось проверить права бота в канале %s", channel, exc_info=True)
        return False
    return member.status in {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}


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
    cached = await _get_cached(session, user_id, channel)
    if not force:
        if cached is not None:
            ttl = timedelta(minutes=settings.subscription_cache_ttl_minutes)
            checked_at = cached.checked_at
            if checked_at.tzinfo is None:
                checked_at = checked_at.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) - checked_at < ttl:
                return cached.is_subscribed

    answer = await check_channel_membership(bot, telegram_id, channel)
    if answer is None:
        # Спросить не удалось — это не ответ «не подписан», и запоминать его
        # нельзя: иначе одна сетевая ошибка запирала бы подписанного человека во
        # всём боте на весь TTL кэша, а сделать он ничего не мог бы.
        # Если прежний вердикт есть — верим ему, он основан на реальном ответе.
        # Если нет — на это обращение не пускаем (fail-closed сохраняется),
        # но и в базу ничего не пишем: следующая попытка спросит заново.
        return cached.is_subscribed if cached is not None else False

    await _store(session, user_id, channel, answer)
    return answer


async def is_fully_subscribed(
    session: AsyncSession,
    bot: Bot,
    user_id: int,
    telegram_id: int,
    force: bool = False,
) -> bool:
    """True — подписан на все обязательные каналы (или админ с включённым байпасом).
    Каналы — из БД (управляются админкой); пустой список → гейт выключен."""
    if settings.admin_bypass_subscription and is_admin(telegram_id):
        return True
    # Premium снимает обязательные подписки (запрос владельца): платишь — нет ОП
    from app.db.models import User
    from app.services.premium import is_premium_active

    user = await session.get(User, user_id)
    if user is not None and is_premium_active(user):
        return True
    from app.services.required_channels import get_required_channels

    for row in await get_required_channels(session):
        if row.kind == "bot":
            continue  # запуск чужого бота проверить нельзя — только кнопка в гейте
        if not await is_channel_subscribed(session, bot, user_id, telegram_id, row.channel, force):
            return False
    return True

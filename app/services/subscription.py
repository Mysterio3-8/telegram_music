"""Обязательная подписка на каналы (TZ §14-17): проверка через getChatMember с TTL-кэшем.

Бот обязан быть администратором проверяемых каналов — иначе Telegram не гарантирует
корректный ответ getChatMember для чужих участников.
"""
import logging
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import SubscriptionStatus
from app.services.users import is_admin

if TYPE_CHECKING:
    from aiogram import Bot

    from app.services.bot_api import BotApi

logger = logging.getLogger(__name__)

# Статусы строками, а не enum aiogram (цикл 7, 15.09): сервис работает и с
# aiogram.Bot (бот, воркеры), и с лёгким BotApi (процесс API — там aiogram не
# загружается ради 38 МБ памяти).
_SUBSCRIBED_STATUSES = {"member", "administrator", "creator"}
_ADMIN_STATUSES = {"administrator", "creator"}


def _status(member) -> str:
    """Статус участника строкой. ⚠️ Не `status in {"member"}` напрямую: у enum
    aiogram хэш считается от ИМЕНИ («MEMBER»), и поиск в множестве строк молча
    промахивается при равенстве значений."""
    return str(getattr(member.status, "value", member.status))


def _telegram_errors() -> tuple[type[BaseException], ...]:
    """Ошибки Telegram обоих клиентов. `aiogram.exceptions` берётся из sys.modules:
    процесс с клиентом aiogram его уже загрузил, а процессу API импорт этого
    модуля не должен тянуть aiogram целиком."""
    from app.services.bot_api import BotApiError

    errors: list[type[BaseException]] = [BotApiError]
    aiogram_exceptions = sys.modules.get("aiogram.exceptions")
    if aiogram_exceptions is not None:
        errors.append(aiogram_exceptions.TelegramAPIError)
    return tuple(errors)

# Вердикт «подписан на всё» в памяти процесса (цикл 5, 14.09). Гейт стоит на
# КАЖДОМ сообщении и нажатии: пользователь, список каналов и статус по каждому
# каналу — ~4 запроса к SQLite на действие, хотя ответ не менялся с прошлой
# минуты. Кэшируется ТОЛЬКО «подписан»: только что подписавшийся не ждёт, пока
# протухнет отказ. Отписка ловится принудительной проверкой (/start, «Я
# подписался») — она выбивает запись — или истечением TTL.
_VERDICT_TTL = 60.0
_VERDICTS_MAX = 50_000
_verdicts: dict[int, float] = {}  # telegram_id → monotonic, до какого момента верим


def forget_subscription_verdicts() -> None:
    """Сбросить все вердикты: изменился список обязательных каналов."""
    _verdicts.clear()


def _remember_verdict(telegram_id: int, subscribed: bool) -> None:
    if not subscribed:
        _verdicts.pop(telegram_id, None)
        return
    if len(_verdicts) >= _VERDICTS_MAX and telegram_id not in _verdicts:
        _verdicts.clear()  # сброс безвреден: следующий запрос просто спросит базу
    _verdicts[telegram_id] = time.monotonic() + _VERDICT_TTL


async def check_channel_membership(
    bot: "Bot | BotApi", telegram_id: int, channel: str
) -> bool | None:
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
    except _telegram_errors():
        logger.warning("getChatMember недоступен channel=%s user=%s", channel, telegram_id, exc_info=True)
        return None
    status = _status(member)
    if status in _SUBSCRIBED_STATUSES:
        return True
    if status == "restricted":
        return bool(getattr(member, "is_member", False))
    return False


async def is_bot_admin_of_channel(bot: "Bot | BotApi", channel: str) -> bool:
    """True — бот является администратором канала. Только это и нужно, чтобы гейт
    мог проверять подписчиков; подписка самого владельца-админа НЕ требуется."""
    try:
        me = await bot.get_me()
        member = await bot.get_chat_member(chat_id=channel, user_id=me.id)
    except _telegram_errors():
        logger.warning("не удалось проверить права бота в канале %s", channel, exc_info=True)
        return False
    return _status(member) in _ADMIN_STATUSES


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
    bot: "Bot | BotApi",
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
    bot: "Bot | BotApi",
    user_id: int,
    telegram_id: int,
    force: bool = False,
) -> bool:
    """True — подписан на все обязательные каналы (или админ с включённым байпасом).
    Каналы — из БД (управляются админкой); пустой список → гейт выключен."""
    if settings.admin_bypass_subscription and is_admin(telegram_id):
        return True
    if not force:
        until = _verdicts.get(telegram_id)
        if until is not None and until > time.monotonic():
            return True
    # Premium снимает обязательные подписки (запрос владельца): платишь — нет ОП
    from app.db.models import User
    from app.services.premium import is_premium_active

    user = await session.get(User, user_id)
    if user is not None and is_premium_active(user):
        return True
    from app.services.required_channels import get_required_channels

    subscribed = True
    for row in await get_required_channels(session):
        if row.kind == "bot":
            continue  # запуск чужого бота проверить нельзя — только кнопка в гейте
        if not await is_channel_subscribed(session, bot, user_id, telegram_id, row.channel, force):
            subscribed = False
            break
    # Premium-вердикт выше не запоминается: истечение подписки должно вернуть
    # гейт сразу, а не через минуту.
    _remember_verdict(telegram_id, subscribed)
    return subscribed

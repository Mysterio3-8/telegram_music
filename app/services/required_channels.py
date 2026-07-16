"""Обязательные каналы подписки: CRUD для админки (TZ §14-17).

Источник правды — таблица required_channels (сеется из .env миграцией).
Пустая таблица → гейт подписки выключен.
"""
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import RequiredChannel, SubscriptionStatus

MAX_CHANNEL_LENGTH = 128


async def get_required_channels(session: AsyncSession) -> list[RequiredChannel]:
    stmt = select(RequiredChannel).order_by(RequiredChannel.id)
    return list((await session.scalars(stmt)).all())


def normalize_channel(raw: str) -> str | None:
    """@handle или -100… (id канала). None — не похоже на канал."""
    value = raw.strip()
    if value.startswith("https://t.me/"):
        value = "@" + value.removeprefix("https://t.me/").strip("/")
    if value.startswith("@") and len(value) > 1 and len(value) <= MAX_CHANNEL_LENGTH:
        return value
    if value.startswith("-100") and value.removeprefix("-").isdigit():
        return value
    return None


async def add_required_channel(
    session: AsyncSession, channel: str, label: str
) -> RequiredChannel | None:
    """None — такой канал уже есть."""
    existing = await session.scalar(
        select(RequiredChannel).where(RequiredChannel.channel == channel)
    )
    if existing is not None:
        return None
    row = RequiredChannel(channel=channel, label=label.strip())
    session.add(row)
    await session.commit()
    return row


async def remove_required_channel(session: AsyncSession, channel_id: int) -> bool:
    row = await session.get(RequiredChannel, channel_id)
    if row is None:
        return False
    # Кэш проверок по каналу больше не нужен (и не должен ожить при повторном добавлении)
    await session.execute(
        delete(SubscriptionStatus).where(SubscriptionStatus.channel == row.channel)
    )
    await session.delete(row)
    await session.commit()
    return True

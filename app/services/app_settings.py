"""Рантайм-флаги, управляемые из админки (хранятся в БД, переживают рестарт)."""
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AppSetting

YOUTUBE_IMPORT_ENABLED = "youtube_import_enabled"


async def get_flag(session: AsyncSession, key: str, default: bool = True) -> bool:
    row = await session.get(AppSetting, key)
    if row is None:
        return default
    return row.value == "1"


async def set_flag(session: AsyncSession, key: str, value: bool) -> None:
    row = await session.get(AppSetting, key)
    if row is None:
        session.add(AppSetting(key=key, value="1" if value else "0"))
    else:
        row.value = "1" if value else "0"
    await session.commit()


async def is_youtube_enabled(session: AsyncSession) -> bool:
    return await get_flag(session, YOUTUBE_IMPORT_ENABLED, default=True)

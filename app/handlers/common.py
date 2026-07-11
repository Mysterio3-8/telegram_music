from aiogram.types import User as TelegramUser
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.services.premium import refresh_premium_status
from app.services.users import TelegramProfile, get_or_create_user


async def ensure_user(session: AsyncSession, tg_user: TelegramUser) -> User:
    profile = TelegramProfile(
        telegram_id=tg_user.id,
        username=tg_user.username,
        first_name=tg_user.first_name,
        language=tg_user.language_code,
    )
    user = await get_or_create_user(session, profile)
    return await refresh_premium_status(session, user)


def format_duration(seconds: int) -> str:
    minutes, secs = divmod(seconds, 60)
    return f"{minutes}:{secs:02d}"

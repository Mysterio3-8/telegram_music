from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Playlist, User, UserLibrary


@dataclass(frozen=True)
class TelegramProfile:
    telegram_id: int
    username: str | None
    first_name: str | None
    language: str | None


async def get_or_create_user(session: AsyncSession, profile: TelegramProfile) -> User:
    user = await session.scalar(select(User).where(User.telegram_id == profile.telegram_id))
    if user is None:
        user = User(telegram_id=profile.telegram_id)
        session.add(user)
    user.username = profile.username
    user.first_name = profile.first_name
    user.language = profile.language
    user.last_login = datetime.now(timezone.utc)
    await session.commit()
    return user


async def get_user_by_telegram_id(session: AsyncSession, telegram_id: int) -> User | None:
    return await session.scalar(select(User).where(User.telegram_id == telegram_id))


async def count_library_tracks(session: AsyncSession, user_id: int) -> int:
    count = await session.scalar(
        select(func.count()).select_from(UserLibrary).where(UserLibrary.user_id == user_id)
    )
    return count or 0


async def count_playlists(session: AsyncSession, user_id: int) -> int:
    count = await session.scalar(
        select(func.count()).select_from(Playlist).where(Playlist.user_id == user_id)
    )
    return count or 0

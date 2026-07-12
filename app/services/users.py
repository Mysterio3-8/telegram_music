from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import Playlist, User, UserLibrary


@dataclass(frozen=True)
class TelegramProfile:
    telegram_id: int
    username: str | None
    first_name: str | None
    language: str | None


async def create_user(session: AsyncSession, telegram_id: int) -> User:
    user = User(telegram_id=telegram_id)
    session.add(user)
    try:
        await session.flush()
        return user
    except IntegrityError:
        # Гонка: параллельный апдейт того же пользователя успел вставить строку
        # между нашим select и insert — откатываемся и берём его строку.
        await session.rollback()
        existing = await session.scalar(select(User).where(User.telegram_id == telegram_id))
        assert existing is not None
        return existing


async def get_or_create_user(session: AsyncSession, profile: TelegramProfile) -> User:
    user = await session.scalar(select(User).where(User.telegram_id == profile.telegram_id))
    if user is None:
        user = await create_user(session, profile.telegram_id)
    user.username = profile.username
    user.first_name = profile.first_name
    user.language = profile.language
    user.last_login = datetime.now(timezone.utc)
    await session.commit()
    return user


async def get_user_by_telegram_id(session: AsyncSession, telegram_id: int) -> User | None:
    return await session.scalar(select(User).where(User.telegram_id == telegram_id))


def is_admin(telegram_id: int) -> bool:
    return telegram_id in settings.admin_id_set


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

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import Playlist, User, UserLibrary
from app.i18n import normalize_language


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


# Как часто обновлять last_login. Его читает только статистика «заходил хоть раз»
# (IS NOT NULL), точность до минут никому не нужна.
_LAST_LOGIN_EVERY = timedelta(minutes=10)


async def get_or_create_user(session: AsyncSession, profile: TelegramProfile) -> User:
    """Пользователь по профилю Telegram; пишет в базу, только если что-то изменилось.

    ⚠️ Зовётся почти из каждого хендлера бота (ensure_user). Раньше на КАЖДОЕ
    сообщение и нажатие безусловно ставился last_login и делался commit — то есть
    пишущая транзакция SQLite на каждое действие, в очереди за единственной
    блокировкой писателя вместе с API и воркерами (цикл 5, 14.09)."""
    user = await session.scalar(select(User).where(User.telegram_id == profile.telegram_id))
    changed = user is None
    if user is None:
        user = await create_user(session, profile.telegram_id)
    for field, value in (
        ("username", profile.username),
        ("first_name", profile.first_name),
        ("language", profile.language),
    ):
        if getattr(user, field) != value:
            setattr(user, field, value)
            changed = True

    now = datetime.now(timezone.utc)
    last = user.last_login
    if last is not None and last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)  # SQLite отдаёт наивное время
    if last is None or now - last >= _LAST_LOGIN_EVERY:
        user.last_login = now
        changed = True

    if changed:
        await session.commit()
    return user


async def get_user_by_telegram_id(session: AsyncSession, telegram_id: int) -> User | None:
    return await session.scalar(select(User).where(User.telegram_id == telegram_id))


def user_language(user: User) -> str:
    """Язык интерфейса: выбранный человеком важнее кода из профиля Telegram."""
    return normalize_language(user.ui_language or user.language)


async def set_user_language(session: AsyncSession, user: User, code: str) -> str:
    """Запоминает выбранный язык. Возвращает то, что реально сохранили."""
    resolved = normalize_language(code)
    user.ui_language = resolved
    await session.commit()
    return resolved


async def set_audio_quality(session: AsyncSession, user: User, choice: str) -> str:
    """Запоминает формат выдачи. Неизвестное значение трактуем как mp3:
    в callback_data может прийти что угодно, а молча выдать платное качество —
    это раздать Premium-функцию всем."""
    from app.services.original_audio import QUALITY_BEST, QUALITY_MP3

    resolved = QUALITY_BEST if choice == QUALITY_BEST else QUALITY_MP3
    user.audio_quality = resolved
    await session.commit()
    return resolved


async def toggle_cover_as_file(session: AsyncSession, user: User) -> bool:
    """Переключает «обложку отдельной картинкой». Возвращает новое состояние."""
    user.cover_as_file = not user.cover_as_file
    await session.commit()
    return user.cover_as_file


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

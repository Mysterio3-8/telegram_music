from collections.abc import AsyncIterator

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.security import decode_access_token
from app.db.base import session_factory
from app.db.models import User
from app.services.premium import is_premium_active
from app.services.users import get_user_by_telegram_id

_bearer = HTTPBearer(auto_error=True)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    session: AsyncSession = Depends(get_db),
) -> User:
    telegram_id = decode_access_token(credentials.credentials)
    if telegram_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Недействительный токен")
    user = await get_user_by_telegram_id(session, telegram_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Пользователь не найден")
    return user


async def require_premium(user: User = Depends(get_current_user)) -> User:
    """Mini App — по подписке (бот бесплатный). Пэйвол жил только в интерфейсе, и
    любой бесплатный аккаунт получал весь API прямыми запросами. Без Premium
    открыты лишь вход, оплата, профиль и документы — они на get_current_user.
    Админы и триал проходят через is_premium_active."""
    if not is_premium_active(user):
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, "Нужен Premium")
    return user

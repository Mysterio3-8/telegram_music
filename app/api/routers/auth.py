from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.schemas import LoginIn, TokenOut
from app.api.security import create_access_token, validate_init_data
from app.services.users import TelegramProfile, get_or_create_user

router = APIRouter(tags=["auth"])


@router.post("/login", response_model=TokenOut)
async def login(payload: LoginIn, session: AsyncSession = Depends(get_db)) -> TokenOut:
    """Авторизация по Telegram WebApp initData (подпись проверяется bot_token)."""
    user_data = validate_init_data(payload.init_data)
    if user_data is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Некорректный initData")

    profile = TelegramProfile(
        telegram_id=int(user_data["id"]),
        username=user_data.get("username"),
        first_name=user_data.get("first_name"),
        language=user_data.get("language_code"),
    )
    await get_or_create_user(session, profile)
    return TokenOut(access_token=create_access_token(profile.telegram_id))

"""Определяет язык интерфейса и кладёт его в `lang` для каждого хендлера.

Иначе каждый экран сам тянул бы пользователя из базы ради одного поля. Здесь
это делается один раз на апдейт, а хендлеру достаточно объявить параметр `lang`.

Приоритет: осознанный выбор (`users.ui_language`) → язык устройства из Telegram
(`language_code`) → русский.
"""
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from sqlalchemy import select

from app.db.base import session_factory
from app.db.models import User
from app.i18n import DEFAULT_LANGUAGE, set_current_language


class I18nMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user = data.get("event_from_user")
        if tg_user is None:
            data["lang"] = set_current_language(DEFAULT_LANGUAGE)
            return await handler(event, data)

        async with session_factory() as session:
            chosen = await session.scalar(
                select(User.ui_language).where(User.telegram_id == tg_user.id)
            )
        data["lang"] = set_current_language(chosen or tg_user.language_code)
        return await handler(event, data)

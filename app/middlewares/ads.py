from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, User

from app.db.base import session_factory
from app.keyboards.premium import ad_keyboard
from app.services.premium import is_premium_active
from app.services.users import get_user_by_telegram_id

AD_TEXT = (
    "📢 Реклама\n\n"
    "Здесь могла быть ваша реклама.\n\n"
    "Отключите рекламу и получите безлимит с 💎 Premium."
)


class AdMiddleware(BaseMiddleware):
    """Показывает рекламу бесплатным пользователям после каждого N-го действия (SPEC §24).

    Счётчики держатся в памяти: терять их при рестарте не страшно (как FSM),
    durable-хранилище переедет в Redis на следующем этапе.
    """

    def __init__(self, frequency: int) -> None:
        self._frequency = frequency
        self._counters: dict[int, int] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        result = await handler(event, data)
        if self._frequency <= 0:
            return result
        user: User | None = data.get("event_from_user")
        if user is None:
            return result

        count = self._counters.get(user.id, 0) + 1
        self._counters[user.id] = count
        if count % self._frequency == 0:
            await self._show_ad(event, user.id)
        return result

    async def _show_ad(self, event: TelegramObject, telegram_id: int) -> None:
        async with session_factory() as session:
            db_user = await get_user_by_telegram_id(session, telegram_id)
        if db_user is not None and is_premium_active(db_user):
            return

        target = event.message if isinstance(event, CallbackQuery) else event
        if isinstance(target, Message):
            await target.answer(AD_TEXT, reply_markup=ad_keyboard())

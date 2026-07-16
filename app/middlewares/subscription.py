"""Гейт обязательной подписки (TZ §16) для всех действий, кроме /start и «Проверить подписку» —
у них своя, всегда принудительная, проверка."""
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.db.base import session_factory
from app.keyboards.subscription import subscription_gate_keyboard
from app.services.subscription import is_fully_subscribed
from app.services.users import get_user_by_telegram_id

GATE_TEXT = (
    "🎵 Для использования ТГ Музыки подпишитесь на наши каналы.\n\n"
    "После подписки нажмите «Проверить подписку»."
)


def _is_exempt(event: TelegramObject) -> bool:
    if isinstance(event, Message):
        return bool(event.text) and event.text.startswith("/start")
    if isinstance(event, CallbackQuery):
        return event.data == "sub:check"
    return True


class SubscriptionMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if _is_exempt(event):
            return await handler(event, data)

        tg_user = data.get("event_from_user")
        if tg_user is None:
            return await handler(event, data)

        async with session_factory() as session:
            db_user = await get_user_by_telegram_id(session, tg_user.id)
            if db_user is None:
                # ещё не проходил /start — пропускаем, там пройдёт полноценная проверка
                return await handler(event, data)
            subscribed = await is_fully_subscribed(session, event.bot, db_user.id, tg_user.id)
            if subscribed:
                return await handler(event, data)
            from app.services.required_channels import get_required_channels

            keyboard = subscription_gate_keyboard(await get_required_channels(session))

        if isinstance(event, CallbackQuery):
            await event.answer("Сначала подпишитесь на каналы", show_alert=True)
            if event.message is not None:
                await event.message.answer(GATE_TEXT, reply_markup=keyboard)
        elif isinstance(event, Message):
            await event.answer(GATE_TEXT, reply_markup=keyboard)
        return None

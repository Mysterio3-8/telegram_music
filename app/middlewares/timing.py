"""Замер времени обработки апдейта (жалоба владельца: «бот отвечает 20 секунд»).

Жалоба на медленный бот бесполезна, пока неизвестно, где именно уходят секунды:
в хендлере, в базе или машина просто задыхается. Здесь — один честный замер на
апдейт: сколько прошло от входа в цепочку мидлварей до ответа хендлера, и какой
хендлер это был.

Пишем только то, что дольше SLOW_SECONDS — на здоровом боте лог остаётся пустым,
и любая строка в нём уже сигнал. Замер идёт по перф-счётчику, а не по системным
часам: перевод времени на сервере не должен рисовать отрицательные задержки.

Мидлварь регистрируется ПЕРВОЙ, до антиспама: интересует полное время, которое
ждал живой человек, включая работу самих мидлварей.
"""
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

logger = logging.getLogger(__name__)

SLOW_SECONDS = 1.0


def describe_event(event: TelegramObject) -> str:
    """Короткая подпись апдейта для лога: что именно тормозило."""
    if isinstance(event, CallbackQuery):
        return f"callback {event.data or '?'}"
    if isinstance(event, Message):
        text = event.text or event.caption or ""
        if text.startswith("/"):
            return f"command {text.split()[0]}"
        if text:
            return "text"
        return "message"
    return type(event).__name__


class TimingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        started = time.perf_counter()
        try:
            return await handler(event, data)
        finally:
            elapsed = time.perf_counter() - started
            if elapsed >= SLOW_SECONDS:
                user = data.get("event_from_user")
                logger.warning(
                    "МЕДЛЕННО: %s — %.1f сек (handler=%s, user=%s)",
                    describe_event(event),
                    elapsed,
                    getattr(data.get("handler"), "callback", None) or "?",
                    getattr(user, "id", "?"),
                )

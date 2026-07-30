"""Антиспам/анти-флуд (требование владельца: защита от спама и DDoS).

Зачем: каждый свободный текст боту запускает поиск (запросы к базе, а при
промахе — скачивание из сети). Без ограничения один человек скриптом положит
и базу, и парсер, и упрётся в лимиты Telegram. Здесь — «дырявое ведро» в памяти:

- не чаще одного действия раз в THROTTLE_SECONDS (мгновенные повторы гасятся);
- не больше BURST_LIMIT действий за BURST_WINDOW секунд;
- превысил — короткая пауза BLOCK_SECONDS, предупреждаем один раз, дальше молчим
  (иначе сами себе устроим флуд ответами).

Счётчики в памяти процесса: бот один, durable-хранилище тут не нужно, а при
рестарте забыть блокировки — не проблема (Redis не трогаем, чтобы флуд не
превращался в запись на диск — именно это уронило прод 2026-07-26).
"""
import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.config import settings

THROTTLE_SECONDS = 0.7  # минимальный интервал между действиями
BURST_LIMIT = 12  # действий за окно
BURST_WINDOW = 10.0  # секунд
BLOCK_SECONDS = 20.0  # пауза после превышения

WARNING_TEXT = "⏳ Слишком много запросов. Подождите пару секунд."


class ThrottlingMiddleware(BaseMiddleware):
    def __init__(self) -> None:
        self._last_action: dict[int, float] = {}
        self._history: dict[int, deque[float]] = defaultdict(deque)
        self._blocked_until: dict[int, float] = {}
        self._warned: set[int] = set()

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user = data.get("event_from_user")
        if tg_user is None or tg_user.id in settings.admin_id_set:
            return await handler(event, data)  # админов не ограничиваем

        user_id = tg_user.id
        now = time.monotonic()

        if now < self._blocked_until.get(user_id, 0.0):
            await self._warn_once(event, user_id)
            return None  # тихо гасим: хендлер не вызывается, нагрузки нет

        history = self._history[user_id]
        history.append(now)
        while history and now - history[0] > BURST_WINDOW:
            history.popleft()

        too_fast = now - self._last_action.get(user_id, 0.0) < THROTTLE_SECONDS
        too_many = len(history) > BURST_LIMIT
        if too_fast or too_many:
            self._blocked_until[user_id] = now + BLOCK_SECONDS
            await self._warn_once(event, user_id)
            return None

        self._last_action[user_id] = now
        self._warned.discard(user_id)  # ведёт себя нормально — снова можно предупредить
        return await handler(event, data)

    async def _warn_once(self, event: TelegramObject, user_id: int) -> None:
        """Предупреждаем один раз на серию: ответ на каждое сообщение флудера —
        это флуд с нашей стороны и лишние запросы к Telegram."""
        if user_id in self._warned:
            return
        self._warned.add(user_id)
        try:
            if isinstance(event, CallbackQuery):
                await event.answer(WARNING_TEXT, show_alert=False)
            elif isinstance(event, Message):
                await event.answer(WARNING_TEXT)
        except Exception:  # noqa: BLE001 — предупреждение best-effort
            pass

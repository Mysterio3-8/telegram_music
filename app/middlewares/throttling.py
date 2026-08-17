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
import logging
import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.config import settings
from app.i18n import t

THROTTLE_SECONDS = 0.7  # минимальный интервал между действиями
BURST_LIMIT = 12  # действий за окно
BURST_WINDOW = 10.0  # секунд
BLOCK_SECONDS = 20.0  # пауза после превышения

logger = logging.getLogger(__name__)

# Жёсткий потолок (требование владельца): больше RAPID_LIMIT действий за секунду
# человек физически не делает — это скрипт. Пауза дольше обычной: обычный флуд
# гасим на 20 секунд, машинный — на минуту.
RAPID_LIMIT = 20
RAPID_WINDOW = 1.0
RAPID_BLOCK_SECONDS = 60.0

# Отдельный потолок на ГРУППУ (пункт 6 спеки). Лимиты по пользователю в общем
# чате не защищают: десять человек по одному действию каждый — это десять
# действий, и каждый в своём праве, а платит за них наш единственный воркер.
# Потолок заметно выше личного: в живом чате нормально, когда музыку ищут
# несколько человек подряд, и глушить их за это нельзя.
CHAT_BURST_LIMIT = 30
CHAT_BURST_WINDOW = 60.0
CHAT_BLOCK_SECONDS = 30.0

# Уборка счётчиков. RETENTION с запасом больше самого длинного окна и самой
# длинной паузы (RAPID_BLOCK_SECONDS = 60), поэтому выброшенная запись повлиять
# на решение уже не могла бы. Реже — копили бы лишнее, чаще — тратили бы такты
# на перебор словарей в горячем пути.
SWEEP_EVERY_SECONDS = 300.0
RETENTION_SECONDS = 600.0


class ThrottlingMiddleware(BaseMiddleware):
    def __init__(self) -> None:
        self._last_action: dict[int, float] = {}
        self._history: dict[int, deque[float]] = defaultdict(deque)
        self._blocked_until: dict[int, float] = {}
        self._warned: set[int] = set()
        # Счётчики по чату — только для групп; в личке чат и человек это одно и
        # то же, и второй лимит там означал бы двойное наказание за то же самое.
        self._chat_history: dict[int, deque[float]] = defaultdict(deque)
        self._chat_blocked_until: dict[int, float] = {}
        self._last_sweep = time.monotonic()

    def _sweep(self, now: float) -> None:
        """Выбрасывает тех, кто давно ничего не делал.

        ⚠️ Очереди меток чистятся сами, а вот КЛЮЧИ раньше не удалялись никогда:
        каждый, кто хоть раз написал боту, навсегда оставлял по записи в шести
        структурах. При нынешних 37 пользователях это незаметно, но бот растёт
        вирально (инлайн в любом чате, рефералка), и на сотне тысяч это
        десятки мегабайт, которые процесс уже не отдаст. На боксе с 961 МБ, где
        воркер трижды падал по OOM, такой рост — вопрос времени.

        Держим только то, что ещё может повлиять на решение: всё старше
        RETENTION уже не влияет ни на одно окно.
        """
        if now - self._last_sweep < SWEEP_EVERY_SECONDS:
            return
        self._last_sweep = now
        cutoff = now - RETENTION_SECONDS

        for key in [k for k, stamp in self._last_action.items() if stamp < cutoff]:
            self._last_action.pop(key, None)
            self._warned.discard(key)
        for key in [k for k, until in self._blocked_until.items() if until < cutoff]:
            self._blocked_until.pop(key, None)
        for key in [k for k, h in self._history.items() if not h or h[-1] < cutoff]:
            self._history.pop(key, None)
        for key in [k for k, h in self._chat_history.items() if not h or h[-1] < cutoff]:
            self._chat_history.pop(key, None)
        for key in [k for k, until in self._chat_blocked_until.items() if until < cutoff]:
            self._chat_blocked_until.pop(key, None)

    def _chat_is_flooding(self, chat_id: int, now: float) -> bool:
        """Ведро на весь чат. True — группа шумит, пропускать не надо."""
        history = self._chat_history[chat_id]
        history.append(now)
        while history and now - history[0] > CHAT_BURST_WINDOW:
            history.popleft()

        if now < self._chat_blocked_until.get(chat_id, 0.0):
            return True
        if len(history) > CHAT_BURST_LIMIT:
            self._chat_blocked_until[chat_id] = now + CHAT_BLOCK_SECONDS
            logger.warning(
                "Флуд в чате %s: %s действий за минуту — пауза %s сек",
                chat_id, len(history), int(CHAT_BLOCK_SECONDS),
            )
            return True
        return False

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
        self._sweep(now)

        # Групповой лимит проверяем ДО личного: в чате шумит не человек, а
        # компания, и гасить надо её целиком. Молча, без предупреждения —
        # писать в общий чат «вы флудите» значит добавить к шуму свой.
        from app.chat_scope import is_group

        if is_group(event, data):
            chat = data.get("event_chat")
            if chat is not None and self._chat_is_flooding(chat.id, now):
                return None

        # Счётчик ведём ДО проверки блокировки: попытки заблокированного тоже
        # приходят на сервер, и именно по ним видно скрипт. Считай мы только
        # пропущенные действия, машинный шквал был бы неотличим от человека,
        # который разок промахнулся по кнопке дважды.
        history = self._history[user_id]
        history.append(now)
        while history and now - history[0] > BURST_WINDOW:
            history.popleft()

        # Жёсткий потолок: больше RAPID_LIMIT действий за секунду — это скрипт.
        # Проверяем раньше остальных правил, чтобы блокировка была длиннее обычной.
        in_last_second = sum(1 for stamp in history if now - stamp <= RAPID_WINDOW)
        if in_last_second > RAPID_LIMIT:
            self._blocked_until[user_id] = now + RAPID_BLOCK_SECONDS
            logger.warning(
                "Флуд: user=%s сделал %s действий за секунду — пауза %s сек",
                user_id, in_last_second, int(RAPID_BLOCK_SECONDS),
            )
            await self._warn_once(event, user_id)
            return None

        if now < self._blocked_until.get(user_id, 0.0):
            await self._warn_once(event, user_id)
            return None  # тихо гасим: хендлер не вызывается, нагрузки нет

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
                await event.answer(t("common.throttled"), show_alert=False)
            elif isinstance(event, Message):
                await event.answer(t("common.throttled"))
        except Exception:  # noqa: BLE001 — предупреждение best-effort
            pass

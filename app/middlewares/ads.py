from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, User

from app.db.base import session_factory
from app.keyboards.premium import ad_keyboard
from app.middlewares import is_payment_message
from app.services.premium import is_premium_active
from app.services.users import get_user_by_telegram_id
from app.i18n import t

# Потолок словаря счётчиков. Раньше запись оставалась навсегда на КАЖДОГО, кто
# хоть раз написал боту: при виральном росте это десятки мегабайт, которые
# процесс бота (15 МБ на 14.09) не вернёт. Сброс счётчиков безвреден — худшее,
# что случится, реклама покажется на пару действий позже.
_COUNTERS_MAX = 50_000


class AdMiddleware(BaseMiddleware):
    """Показывает рекламу бесплатным пользователям после каждого N-го действия (SPEC §24).

    Счётчики держатся в памяти: терять их при рестарте не страшно (как FSM).
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
        # Реклама Premium сразу за «спасибо за донат» — худший момент для неё.
        if self._frequency <= 0 or is_payment_message(event):
            return result
        # В группах рекламу не показываем (пункт 6 спеки): «купи Premium» в
        # чужом чате — это спам от нашего имени, за который бота выгоняют, а не
        # покупают подписку.
        from app.chat_scope import is_private

        if not is_private(event, data):
            return result
        user: User | None = data.get("event_from_user")
        if user is None:
            return result

        if len(self._counters) >= _COUNTERS_MAX and user.id not in self._counters:
            self._counters.clear()
        count = self._counters.get(user.id, 0) + 1
        self._counters[user.id] = count % self._frequency
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
            # Текст берётся здесь, а не при импорте модуля: константа уровня модуля
            # вычислялась один раз на языке по умолчанию, и англоязычный,
            # испанский, турецкий пользователь получал рекламу по-русски.
            # Язык запроса уже лежит в ContextVar — I18nMiddleware стоит раньше.
            await target.answer(t("ads.text"), reply_markup=ad_keyboard())

"""Отправка в Telegram, которая переживает флуд-контроль.

Живой прогон 25.09: альбом «Dragonborn» пришёл 20 из 23. Три трека не дошли не
из-за источника — Telegram ответил на минт в архивный канал «Too Many Requests:
retry after 16», и импорт сдался. Канал принимает около 20 сообщений в минуту,
а альбом минтит трек за треком быстрее. Подождать 16 секунд дешевле, чем
потерять трек.

Исключение из правила «services не знают aiogram» — то же, что у импортёров,
которые минтят file_id: это их общая часть.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

ATTEMPTS = 3
# Дольше минуты не ждём: человек ждёт трек, а воркер — очередь
MAX_WAIT_SECONDS = 60


async def with_flood_retry(call: Callable[[], Awaitable[T]], what: str = "отправка") -> T:
    """Вызывает `call`, а на флуд-контроль ждёт, сколько сказал Telegram, и повторяет.

    `call` — фабрика корутины, а не корутина: повтор требует нового вызова.
    Файлы для повтора годятся — BufferedInputFile держит байты и читается заново.
    """
    # Импорт здесь, а не наверху: модуль подтягивают сервисы, которые импортирует
    # и API, а процессу API aiogram не нужен — это ~95 МБ (test_api_process_imports)
    from aiogram.exceptions import TelegramRetryAfter

    for attempt in range(1, ATTEMPTS + 1):
        try:
            return await call()
        except TelegramRetryAfter as exc:
            if attempt == ATTEMPTS or exc.retry_after > MAX_WAIT_SECONDS:
                raise
            logger.info("%s: флуд-контроль Telegram, жду %s сек (попытка %s)", what, exc.retry_after, attempt)
            await asyncio.sleep(exc.retry_after + 1)
    raise AssertionError("недостижимо")

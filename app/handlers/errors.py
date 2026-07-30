"""Глобальный обработчик ошибок (требование владельца: бот не должен падать).

aiogram и так не роняет весь polling-луп на исключении в одном хендлере — оно
логируется штатным логгером и цикл продолжается. Но без явного обработчика
пользователь в ответ получает молчание (выглядит как «завис»), а traceback
теряется в потоке INFO-логов. Здесь: пишем ошибку явно (видно через
`journalctl -u tg-music-bot | grep ERROR`) и отвечаем пользователю вместо
тишины — вернуть True обязательно, иначе aiogram решит, что ошибка не обработана.
"""
import logging

from aiogram import Router
from aiogram.types import ErrorEvent

logger = logging.getLogger(__name__)

router = Router()

FRIENDLY_TEXT = "⚠️ Что-то пошло не так. Уже разбираемся — попробуйте ещё раз через минуту."


@router.errors()
async def handle_any_error(event: ErrorEvent) -> bool:
    logger.error("Необработанная ошибка в хендлере", exc_info=event.exception)

    update = event.update
    target = update.message or (update.callback_query.message if update.callback_query else None)
    if target is not None:
        try:
            await target.answer(FRIENDLY_TEXT)
        except Exception:  # noqa: BLE001 — уведомление best-effort, не плодим новую ошибку
            logger.warning("Не удалось уведомить пользователя об ошибке", exc_info=True)

    if update.callback_query is not None:
        try:
            await update.callback_query.answer()
        except Exception:  # noqa: BLE001 — закрыть «часики» на кнопке, не критично при неудаче
            pass

    return True  # ошибка обработана — aiogram не должен пытаться поднять её дальше

"""Быстрые команды Telegram (TZ §12-13): /start видят все, /admin — только админы
через персональный scope (BotCommandScopeChat). Backend всё равно проверяет
is_admin на каждый вызов /admin — скрытие в меню не защита."""
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramUnauthorizedError
from aiogram.types import (
    BotCommand,
    BotCommandScopeAllGroupChats,
    BotCommandScopeChat,
    BotCommandScopeDefault,
)

from app.config import settings

logger = logging.getLogger(__name__)

DEFAULT_COMMANDS = [
    BotCommand(command="start", description="Главное меню"),
    BotCommand(command="premium", description="Premium — Stars или карта"),
    BotCommand(command="donate", description="Поддержать проект"),
]
ADMIN_COMMANDS = DEFAULT_COMMANDS + [BotCommand(command="admin", description="Админ-панель")]


async def _set_commands(bot: Bot, commands: list[BotCommand], scope, what: str) -> None:
    """Выставить команды, не роняя запуск бота из-за отказа Telegram.

    ⚠️ Меню команд — украшение: бот полностью работоспособен и без него, человек
    просто не увидит подсказку. А вот исключение здесь улетает из main() ещё до
    старта polling, процесс умирает, и `Restart=always` заводит петлю — каждый
    заход это полный импорт Python с aiogram, четверть единственного ядра
    круглосуточно. Ровно так 16.08 крутился `tg-music-moved` (511 рестартов) и
    01.08 `tg-music-worker` (load average 15). Разменивать работающего бота на
    подпись в меню нельзя.
    """
    try:
        await bot.set_my_commands(commands, scope=scope)
    except TelegramUnauthorizedError:
        # ⚠️ Unauthorized — ПОДКЛАСС TelegramAPIError, и раньше он молча уходил в
        # warning вместе с сетевыми отказами. Но это не «не получилось сейчас», а
        # «токен не годится»: само не пройдёт, и разбираться с этим должен main().
        raise
    except TelegramAPIError:
        logger.warning("Не удалось выставить команды (%s) — бот работает без них", what, exc_info=True)


async def setup_bot_commands(bot: Bot) -> None:
    await _set_commands(bot, DEFAULT_COMMANDS, BotCommandScopeDefault(), "по умолчанию")
    # В группах команд нет вовсе (пункт 6 спеки): /start и /premium — личные
    # экраны, они там не работают, а предлагать в меню то, что молчит, хуже, чем
    # не предлагать ничего. Способ позвать бота в чате один — упомянуть его.
    await _set_commands(bot, [], BotCommandScopeAllGroupChats(), "группы")
    for admin_id in settings.admin_id_set:
        # Telegram требует, чтобы админ хотя бы раз написал боту, прежде чем
        # принять персональный scope команд — не блокируем запуск бота из-за этого.
        await _set_commands(
            bot, ADMIN_COMMANDS, BotCommandScopeChat(chat_id=admin_id), f"admin={admin_id}"
        )

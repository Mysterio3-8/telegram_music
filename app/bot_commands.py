"""Быстрые команды Telegram (TZ §12-13): /start видят все, /admin — только админы
через персональный scope (BotCommandScopeChat). Backend всё равно проверяет
is_admin на каждый вызов /admin — скрытие в меню не защита."""
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
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
]
ADMIN_COMMANDS = DEFAULT_COMMANDS + [BotCommand(command="admin", description="Админ-панель")]


async def setup_bot_commands(bot: Bot) -> None:
    await bot.set_my_commands(DEFAULT_COMMANDS, scope=BotCommandScopeDefault())
    # В группах команд нет вовсе (пункт 6 спеки): /start и /settings — личные
    # экраны, они там не работают, а предлагать в меню то, что молчит, хуже, чем
    # не предлагать ничего. Способ позвать бота в чате один — упомянуть его.
    try:
        await bot.set_my_commands([], scope=BotCommandScopeAllGroupChats())
    except TelegramAPIError:
        logger.warning("Не удалось очистить команды для групп", exc_info=True)
    for admin_id in settings.admin_id_set:
        try:
            await bot.set_my_commands(ADMIN_COMMANDS, scope=BotCommandScopeChat(chat_id=admin_id))
        except TelegramAPIError:
            # Telegram требует, чтобы админ хотя бы раз написал боту, прежде чем
            # принять персональный scope команд — не блокируем запуск бота из-за этого.
            logger.warning("Не удалось выставить команды для admin=%s", admin_id, exc_info=True)

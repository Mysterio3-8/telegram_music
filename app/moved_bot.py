"""Бот-указатель на старом токене: «мы переехали».

Юзернейм у Telegram сменить на занятый нельзя, поэтому пришлось завести нового
бота. Старый остаётся жить только ради тех, у кого он в списке чатов: на любое
сообщение или нажатие отвечает ссылкой на новый бот и больше ничего не умеет.

Токен старого бота — MOVED_BOT_TOKEN в .env (основной BOT_TOKEN уже новый).
Запуск: python -m app.moved_bot
"""
import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.exceptions import TelegramUnauthorizedError
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.config import settings
from app.i18n import normalize_language, t

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

dp = Dispatcher()


def _keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("moved.button", lang),
                    url=f"https://t.me/{settings.bot_username}",
                )
            ]
        ]
    )


@dp.message()
async def on_any_message(message: Message) -> None:
    lang = normalize_language(message.from_user.language_code if message.from_user else None)
    await message.answer(
        t("moved.text", lang, username=settings.bot_username),
        reply_markup=_keyboard(lang),
        parse_mode="HTML",
    )


@dp.callback_query()
async def on_any_callback(callback: CallbackQuery) -> None:
    lang = normalize_language(callback.from_user.language_code)
    if callback.message is not None:
        await callback.message.answer(
            t("moved.text", lang, username=settings.bot_username),
            reply_markup=_keyboard(lang),
            parse_mode="HTML",
        )
    await callback.answer()


# Код выхода «токен не годится». Systemd получает его из
# RestartPreventExitStatus и перестаёт поднимать юнит.
EXIT_BAD_TOKEN = 78  # EX_CONFIG


async def main() -> int:
    if not settings.moved_bot_token:
        logging.warning("MOVED_BOT_TOKEN не задан — старому боту нечего делать")
        return EXIT_BAD_TOKEN
    bot = Bot(token=settings.moved_bot_token)
    try:
        # Меню и команды старого бота больше не актуальны — чистим, чтобы не путать
        await bot.delete_my_commands()
        await dp.start_polling(bot)
    except TelegramUnauthorizedError:
        # 🔴 Найдено 16.08: токен старого бота отозван, и юнит падал на этой самой
        # строке 511 раз подряд. `Restart=always` тут не защита, а генератор
        # нагрузки: каждый заход — полный импорт Python с aiogram, то есть
        # четверть единственного ядра, и так круглосуточно. Ровно этим 01.08
        # `tg-music-worker` довёл load average до 15.
        #
        # Отозванный токен сам не починится, поэтому выходим кодом, по которому
        # systemd прекращает попытки, и пишем в журнал, что делать человеку.
        logging.error(
            "MOVED_BOT_TOKEN отозван — Telegram отвечает Unauthorized. "
            "Указатель «мы переехали» работать не будет, пока в .env не появится "
            "действующий токен старого бота. Юнит больше не перезапускается."
        )
        return EXIT_BAD_TOKEN
    finally:
        await bot.session.close()
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    raise SystemExit(asyncio.run(main()))

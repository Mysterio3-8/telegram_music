"""Бот поддержки @suptgmusic_bot (блок F): собирает жалобы/отзывы/предложения.

Отдельный процесс со своим polling — file_id медиа привязан к боту, поэтому
пересылка владельцу работает только из того же бота, что принял сообщение.
Пользователь приходит по ссылке из основного бота.

Запуск: python -m app.support_bot (нужен SUPPORT_BOT_TOKEN в .env).
"""
import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.config import settings
from app.services.support import (
    CATEGORIES,
    rate_limited,
    text_too_short,
    ticket_header,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Ticket(StatesGroup):
    choosing = State()
    writing = State()


def _category_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=label, callback_data=data)]
                         for data, label in CATEGORIES.items()]
    )


async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.set_state(Ticket.choosing)
    await message.answer(
        "👋 Это поддержка Infinity Music.\n\n"
        "Выберите тему обращения — а затем опишите подробно. Можно приложить "
        "скриншот, фото, видео, аудио или документ, чтобы мы быстрее разобрались.",
        reply_markup=_category_keyboard(),
    )


async def cb_category(callback: CallbackQuery, state: FSMContext) -> None:
    label = CATEGORIES.get(callback.data)
    if label is None:
        await callback.answer()
        return
    await state.set_state(Ticket.writing)
    await state.update_data(category=label)
    await callback.message.answer(
        f"Тема: {label}.\nНапишите сообщение подробно — чем детальнее, тем лучше. "
        "При необходимости приложите файл."
    )
    await callback.answer()


async def process_ticket(message: Message, state: FSMContext) -> None:
    owner = settings.effective_support_chat_id
    if owner is None:
        await message.answer("Поддержка временно недоступна. Попробуйте позже.")
        return

    # Мягкий антиспам: слишком короткий текст без вложений — просим дополнить
    caption = message.text or message.caption or ""
    has_media = bool(
        message.photo or message.video or message.audio or message.document or message.voice
    )
    if not has_media and text_too_short(caption):
        await message.answer(
            "Опишите, пожалуйста, подробнее (хотя бы пару предложений) — так мы "
            "поймём проблему и быстрее поможем."
        )
        return
    if rate_limited(message.from_user.id):
        await message.answer("Вы отправили несколько обращений подряд. Подождите немного 🙏")
        return

    data = await state.get_data()
    header = ticket_header(data.get("category", "Обращение"), message.from_user)
    bot = message.bot
    await bot.send_message(owner, header)
    # copy_message переносит и текст, и вложение — тем же ботом, file_id валиден
    await bot.copy_message(chat_id=owner, from_chat_id=message.chat.id, message_id=message.message_id)

    await message.answer("Спасибо! Обращение отправлено — мы прочитаем и ответим на улучшениях 💛")
    await state.set_state(Ticket.choosing)


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher()
    dp.message.register(cmd_start, CommandStart())
    dp.callback_query.register(cb_category, F.data.in_(CATEGORIES.keys()))
    dp.message.register(process_ticket, Ticket.writing)
    return dp


async def main() -> None:
    if not settings.support_bot_token:
        raise SystemExit("SUPPORT_BOT_TOKEN не задан — бот поддержки не запускается")
    bot = Bot(token=settings.support_bot_token)
    dp = build_dispatcher()
    logger.info("Support bot polling…")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

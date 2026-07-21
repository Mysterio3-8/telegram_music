"""Перенос музыки из других сервисов (скрин VK «Перенос из других сервисов»).

Ссылка на плейлист Spotify/Яндекс.Музыки — или текстовый список строками
«Артист — Название» (работает для ВК и любого другого сервиса). Разбор ссылки
быстрый, сам перенос — в Celery: сотни треков в хендлере держать нельзя.
"""
import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.config import settings
from app.db.base import session_factory
from app.handlers.common import ensure_user
from app.services.playlist_transfer.parsers import (
    TransferSourceError,
    detect_service,
    fetch_playlist,
    parse_text_list,
)

logger = logging.getLogger(__name__)

router = Router()

MAX_PREVIEW = 5


class Transfer(StatesGroup):
    waiting_source = State()
    waiting_confirm = State()


def _confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📥 Перенести", callback_data="tr:go")],
            [InlineKeyboardButton(text="◀️ Отмена", callback_data="tr:cancel")],
        ]
    )


PROMPT = (
    "📥 <b>Перенос музыки из других сервисов</b>\n\n"
    "Пришлите:\n"
    "▪️ ссылку на публичный плейлист <b>Spotify</b> или <b>Яндекс.Музыки</b>;\n"
    "▪️ ссылку на <b>SoundCloud</b> (профиль, лайки, сет);\n"
    "▪️ или просто список текстом, по строке на трек:\n"
    "<code>Kizaru — Fendi\nBig Baby Tape — Gimme the Loot</code>\n\n"
    "Так переносится музыка из ВКонтакте и откуда угодно ещё: скопируйте список "
    "и пришлите сюда.\n\n"
    "Мы найдём эти треки в нашей базе, а чего нет — загрузим."
)


@router.message(Command("transfer"))
async def cmd_transfer(message: Message, state: FSMContext) -> None:
    await state.set_state(Transfer.waiting_source)
    await message.answer(PROMPT, parse_mode="HTML")


@router.callback_query(F.data == "menu:transfer")
async def cb_transfer(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Transfer.waiting_source)
    await callback.message.answer(PROMPT, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "tr:cancel")
async def cb_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("Перенос отменён.")
    await callback.answer()


@router.message(Transfer.waiting_source, F.text)
async def process_source(message: Message, state: FSMContext) -> None:
    text = message.text.strip()

    # SoundCloud уже умеет качать напрямую — отправляем в свой мастер
    if detect_service(text) == "soundcloud":
        await state.clear()
        await message.answer(
            "Ссылки SoundCloud принимает мастер «Загрузить трек» — он скачает "
            "аудио напрямую, без поиска совпадений."
        )
        return

    status = await message.answer("Читаю список…")
    try:
        items = await fetch_playlist(text) if text.startswith("http") else parse_text_list(text)
    except TransferSourceError as error:
        await status.edit_text(str(error))
        return
    except Exception:  # noqa: BLE001 — сеть/формат чужого сервиса
        logger.exception("Перенос: не удалось разобрать источник")
        await status.edit_text("Не удалось прочитать список. Попробуйте прислать текстом.")
        return

    if not items:
        await status.edit_text(
            "Не нашёл треков. Формат строки: <code>Артист — Название</code>.",
            parse_mode="HTML",
        )
        return

    await state.update_data(transfer_items=[{"artist": i.artist, "title": i.title} for i in items])
    await state.set_state(Transfer.waiting_confirm)
    preview = "\n".join(f"▪️ {i.artist} — {i.title}" for i in items[:MAX_PREVIEW])
    tail = f"\n…и ещё {len(items) - MAX_PREVIEW}" if len(items) > MAX_PREVIEW else ""
    await status.edit_text(
        f"Нашёл треков: <b>{len(items)}</b>\n\n{preview}{tail}\n\nПереносим в вашу библиотеку?",
        parse_mode="HTML",
        reply_markup=_confirm_keyboard(),
    )


@router.callback_query(F.data == "tr:go")
async def cb_go(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    items = data.get("transfer_items") or []
    await state.clear()
    if not items:
        await callback.answer("Список пуст — начните заново", show_alert=True)
        return

    async with session_factory() as session:
        await ensure_user(session, callback.from_user)

    if not settings.effective_celery_broker:
        await callback.answer()
        await callback.message.edit_text("Перенос временно недоступен — фоновые задачи выключены.")
        return

    from app.tasks.transfer import transfer_playlist_task

    try:
        transfer_playlist_task.delay(items, callback.from_user.id)
    except Exception:  # noqa: BLE001
        logger.exception("Перенос: не удалось поставить задачу")
        await callback.answer()
        await callback.message.edit_text("Не удалось запустить перенос — попробуйте позже.")
        return

    await callback.answer()
    await callback.message.edit_text(
        f"📥 Переношу {len(items)} треков. Это займёт время — пришлю отчёт, когда закончу.\n\n"
        "Найденное в базе появится в библиотеке сразу."
    )

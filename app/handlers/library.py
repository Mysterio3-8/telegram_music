import math

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from aiogram.types import User as TelegramUser

from app.config import settings
from app.db.base import session_factory
from app.handlers.common import ensure_user
from app.keyboards.library import library_keyboard, search_results_keyboard
from app.services.library import get_library_page, search_library
from app.services.users import count_library_tracks

router = Router()


class LibrarySearch(StatesGroup):
    waiting_query = State()


def _library_text(track_count: int) -> str:
    if track_count == 0:
        return "🎵 Библиотека\n\nВсего треков: 0\n\nБиблиотека пуста — добавьте треки через поиск или загрузку."
    return f"🎵 Библиотека\n\nВсего треков: {track_count}"


async def show_library_page(message: Message, tg_user: TelegramUser, page: int) -> None:
    async with session_factory() as session:
        user = await ensure_user(session, tg_user)
        track_count = await count_library_tracks(session, user.id)
        total_pages = max(1, math.ceil(track_count / settings.page_size))
        page = min(max(page, 1), total_pages)
        tracks = await get_library_page(session, user.id, page)
    await message.edit_text(
        _library_text(track_count),
        reply_markup=library_keyboard(tracks, page, total_pages),
    )


@router.callback_query(F.data == "menu:library")
async def cb_library(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(None)  # данные поиска сохраняем — экраны выше остаются рабочими
    await show_library_page(callback.message, callback.from_user, page=1)
    await callback.answer()


@router.callback_query(F.data.startswith("lib:page:"))
async def cb_library_page(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(None)
    page = int(callback.data.split(":")[2])
    await show_library_page(callback.message, callback.from_user, page)
    await callback.answer()


@router.callback_query(F.data == "lib:search")
async def cb_library_search(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(LibrarySearch.waiting_query)
    await callback.message.answer("Введите название")
    await callback.answer()


@router.message(LibrarySearch.waiting_query, F.text)
async def process_search_query(message: Message, state: FSMContext) -> None:
    await state.set_state(None)
    async with session_factory() as session:
        user = await ensure_user(session, message.from_user)
        tracks = await search_library(session, user.id, message.text)
    if not tracks:
        await message.answer(
            "Ничего не найдено в вашей библиотеке.",
            reply_markup=search_results_keyboard([]),
        )
        return
    await message.answer(
        f"Найдено в библиотеке: {len(tracks)}",
        reply_markup=search_results_keyboard(tracks),
    )


# «Случайный трек» стал режимом «Микс» — обрабатывается в handlers/player.py (q:mix)

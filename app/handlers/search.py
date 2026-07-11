import math

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from app.config import settings
from app.db.base import session_factory
from app.handlers.common import format_duration
from app.keyboards.search import (
    instrumental_card_keyboard,
    instrumental_results_keyboard,
    track_results_keyboard,
)
from app.services.search import get_instrumental, search_instrumentals, search_tracks

router = Router()


class TrackSearch(StatesGroup):
    waiting_query = State()


class InstrumentalSearch(StatesGroup):
    waiting_query = State()


def _results_text(query: str, total: int) -> str:
    if total == 0:
        return f"По запросу «{query}» ничего не найдено."
    return f"🔍 Результаты по запросу «{query}»\n\nНайдено: {total}"


# --- Поиск треков ---


@router.callback_query(F.data == "menu:search")
async def cb_search(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(TrackSearch.waiting_query)
    await callback.message.answer("Введите название трека")
    await callback.answer()


async def _render_track_results(
    message: Message, state: FSMContext, query: str, page: int, edit: bool
) -> None:
    async with session_factory() as session:
        tracks, total = await search_tracks(session, query, page)
    total_pages = max(1, math.ceil(total / settings.page_size))
    await state.update_data(track_query=query, track_page=page)
    text = _results_text(query, total)
    keyboard = track_results_keyboard(tracks, page, total_pages)
    if edit:
        await message.edit_text(text, reply_markup=keyboard)
    else:
        await message.answer(text, reply_markup=keyboard)


@router.message(TrackSearch.waiting_query, F.text)
async def process_track_query(message: Message, state: FSMContext) -> None:
    await state.set_state(None)  # выходим из ожидания, но данные запроса сохраняем
    await _render_track_results(message, state, message.text, page=1, edit=False)


@router.callback_query(F.data.startswith("st:page:"))
async def cb_track_results_page(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    query = data.get("track_query")
    if not query:
        await callback.answer("Повторите поиск — запрос устарел", show_alert=True)
        return
    page = int(callback.data.split(":")[2])
    await _render_track_results(callback.message, state, query, page, edit=True)
    await callback.answer()


async def rerender_track_results(callback: CallbackQuery, state: FSMContext) -> bool:
    """Возврат из карточки трека к результатам поиска. False — запрос устарел. Не answer-ит."""
    data = await state.get_data()
    query = data.get("track_query")
    if not query:
        return False
    await _render_track_results(
        callback.message, state, query, data.get("track_page", 1), edit=True
    )
    return True


# --- Поиск минусов ---


@router.callback_query(F.data == "menu:instrumentals")
async def cb_instrumentals(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(InstrumentalSearch.waiting_query)
    await callback.message.answer("Введите название")
    await callback.answer()


async def _render_instrumental_results(
    message: Message, state: FSMContext, query: str, page: int, edit: bool
) -> None:
    async with session_factory() as session:
        instrumentals, total = await search_instrumentals(session, query, page)
    total_pages = max(1, math.ceil(total / settings.page_size))
    await state.update_data(ins_query=query, ins_page=page)
    text = _results_text(query, total)
    keyboard = instrumental_results_keyboard(instrumentals, page, total_pages)
    if edit:
        await message.edit_text(text, reply_markup=keyboard)
    else:
        await message.answer(text, reply_markup=keyboard)


@router.message(InstrumentalSearch.waiting_query, F.text)
async def process_instrumental_query(message: Message, state: FSMContext) -> None:
    await state.set_state(None)
    await _render_instrumental_results(message, state, message.text, page=1, edit=False)


@router.callback_query(F.data.startswith("si:page:"))
async def cb_instrumental_results_page(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    query = data.get("ins_query")
    if not query:
        await callback.answer("Повторите поиск — запрос устарел", show_alert=True)
        return
    page = int(callback.data.split(":")[2])
    await _render_instrumental_results(callback.message, state, query, page, edit=True)
    await callback.answer()


@router.callback_query(F.data == "si:back")
async def cb_instrumental_back(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    query = data.get("ins_query")
    if not query:
        await callback.answer("Повторите поиск — запрос устарел", show_alert=True)
        return
    await _render_instrumental_results(
        callback.message, state, query, data.get("ins_page", 1), edit=True
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ins:"))
async def cb_instrumental_card(callback: CallbackQuery) -> None:
    instrumental_id = int(callback.data.split(":")[1])
    async with session_factory() as session:
        instrumental = await get_instrumental(session, instrumental_id)
    if instrumental is None:
        await callback.answer("Минус не найден", show_alert=True)
        return
    await callback.message.edit_text(
        f"🎼 {instrumental.title} (Минус)\n\n"
        f"Исполнитель: {instrumental.artist}\n"
        f"Длительность: {format_duration(instrumental.duration)}",
        reply_markup=instrumental_card_keyboard(),
    )
    await callback.answer()

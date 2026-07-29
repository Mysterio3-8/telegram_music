"""Быстрый поиск в боте (запрос владельца): пользователь пишет боту любой текст —
название и/или исполнителя — и получает СПИСОК найденных треков кнопками
(формат по скринам: «2:19 kizaru - AFK» + пагинация). Тап по кнопке — трек
приходит аудиосообщением.

Нашли в базе → показываем список. Не нашли → скрытый поисковый парсер тихо
ищет в сети, трек приходит следом.

Регистрируется последним: перехватывает только свободный текст без активного FSM
(мастера загрузки/поиска/админки со своими состояниями срабатывают раньше).
"""
import logging
import math

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.db.base import session_factory
from app.handlers.common import ensure_user
from app.handlers.delivery import send_track_audio
from app.keyboards.quick_search import PAGE_SIZE, quick_search_keyboard
from app.services.library import get_track
from app.services.search import search_tracks

logger = logging.getLogger(__name__)

router = Router()

_QUERY_KEY = "qs_query"  # запрос живёт в FSM: в callback_data он не помещается


def _results_title(query: str) -> str:
    return f'🎵 Треки по запросу «{query}»'


async def _show_page(message: Message, query: str, page: int, edit: bool) -> bool:
    """Рисует страницу выдачи. False — в базе ничего нет."""
    async with session_factory() as session:
        tracks, total = await search_tracks(session, query, page=page, page_size=PAGE_SIZE)
    if not tracks:
        return False

    total_pages = max(1, math.ceil(total / PAGE_SIZE))
    markup = quick_search_keyboard(tracks, page, total_pages)
    text = _results_title(query)
    if edit:
        await message.edit_text(text, reply_markup=markup)
    else:
        await message.answer(text, reply_markup=markup)
    return True


@router.message(F.text & ~F.text.startswith("/"))
async def quick_search(message: Message, state: FSMContext) -> None:
    query = message.text.strip()
    if not query:
        return
    async with session_factory() as session:
        await ensure_user(session, message.from_user)

    await state.update_data(**{_QUERY_KEY: query})
    if await _show_page(message, query, page=1, edit=False):
        return

    # В базе нет — прячем факт парсера, просто «ищу»
    try:
        from app.tasks.search_fetch import search_fetch

        search_fetch.delay(query=query, telegram_id=message.chat.id, chat_id=message.chat.id)
        await message.answer("🔎 Ищу трек — пришлю через минуту.")
    except Exception:  # noqa: BLE001 — брокер недоступен
        await message.answer("Пока не нашёл. Попробуйте уточнить название и исполнителя.")


@router.callback_query(F.data.startswith("qs:p:"))
async def quick_search_page(callback: CallbackQuery, state: FSMContext) -> None:
    page = int(callback.data.split(":")[2])
    query = (await state.get_data()).get(_QUERY_KEY, "")
    if not query:
        await callback.answer("Повторите поиск", show_alert=True)
        return
    await _show_page(callback.message, query, page=page, edit=True)
    await callback.answer()


@router.callback_query(F.data.startswith("qs:t:"))
async def quick_search_send(callback: CallbackQuery) -> None:
    track_id = int(callback.data.split(":")[2])
    async with session_factory() as session:
        user = await ensure_user(session, callback.from_user)
        track = await get_track(session, track_id)
        if track is None:
            await callback.answer("Трек не найден", show_alert=True)
            return
        await callback.answer("Отправляю…")
        await send_track_audio(callback.bot, callback.message.chat.id, session, user, track)


@router.callback_query(F.data == "qs:noop")
async def quick_search_noop(callback: CallbackQuery) -> None:
    await callback.answer()

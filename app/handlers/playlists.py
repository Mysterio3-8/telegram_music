import math

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from app.config import settings
from app.db.base import session_factory
from app.handlers.common import ensure_user
from app.keyboards.playlists import (
    confirm_delete_keyboard,
    playlist_view_keyboard,
    playlists_keyboard,
)
from app.services.playlists import (
    count_playlist_tracks,
    create_playlist,
    delete_playlist,
    get_playlist,
    get_playlist_tracks_page,
    get_playlists_page,
)
from app.services.premium import can_create_playlist
from app.services.users import count_playlists

router = Router()

MAX_PLAYLIST_TITLE_LENGTH = 128


class PlaylistCreate(StatesGroup):
    waiting_title = State()


async def _render_playlists(message: Message, telegram_user, page: int, edit: bool) -> None:
    async with session_factory() as session:
        user = await ensure_user(session, telegram_user)
        total = await count_playlists(session, user.id)
        total_pages = max(1, math.ceil(total / settings.page_size))
        page = min(max(page, 1), total_pages)
        playlists = await get_playlists_page(session, user.id, page)
    text = f"📂 Плейлисты\n\nВсего: {total}"
    if total == 0:
        text += "\n\nПлейлистов пока нет — создайте первый."
    keyboard = playlists_keyboard(playlists, page, total_pages)
    if edit:
        await message.edit_text(text, reply_markup=keyboard)
    else:
        await message.answer(text, reply_markup=keyboard)


async def show_playlist_view(callback: CallbackQuery, playlist_id: int, page: int) -> bool:
    """True — экран показан; False — плейлист не найден. Callback не answer-ит."""
    async with session_factory() as session:
        user = await ensure_user(session, callback.from_user)
        playlist = await get_playlist(session, playlist_id)
        if playlist is None or playlist.user_id != user.id:
            return False
        total = await count_playlist_tracks(session, playlist_id)
        total_pages = max(1, math.ceil(total / settings.page_size))
        page = min(max(page, 1), total_pages)
        tracks = await get_playlist_tracks_page(session, playlist_id, page)
    text = f"Название:\n{playlist.title}\n\nВсего треков:\n{total}"
    if total == 0:
        text += "\n\nПлейлист пуст — добавляйте треки из карточки трека."
    await callback.message.edit_text(
        text, reply_markup=playlist_view_keyboard(tracks, playlist_id, page, total_pages)
    )
    return True


@router.callback_query(F.data == "menu:playlists")
async def cb_playlists(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await _render_playlists(callback.message, callback.from_user, page=1, edit=True)
    await callback.answer()


@router.callback_query(F.data.startswith("pls:page:"))
async def cb_playlists_page(callback: CallbackQuery) -> None:
    page = int(callback.data.split(":")[2])
    await _render_playlists(callback.message, callback.from_user, page, edit=True)
    await callback.answer()


@router.callback_query(F.data == "pls:new")
async def cb_playlist_new(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(PlaylistCreate.waiting_title)
    await callback.message.answer("Введите название плейлиста")
    await callback.answer()


@router.message(PlaylistCreate.waiting_title, F.text)
async def process_playlist_title(message: Message, state: FSMContext) -> None:
    title = message.text.strip()
    if not title or len(title) > MAX_PLAYLIST_TITLE_LENGTH:
        await message.answer(f"Название должно быть от 1 до {MAX_PLAYLIST_TITLE_LENGTH} символов. Попробуйте ещё раз.")
        return
    async with session_factory() as session:
        user = await ensure_user(session, message.from_user)
        if not await can_create_playlist(session, user):
            await state.clear()
            await message.answer(
                f"На бесплатном тарифе доступно {settings.free_playlist_limit} плейлистов.\n"
                "💎 Premium снимает лимит — раздел «Купить Premium» в меню."
            )
            return
        await create_playlist(session, user.id, title)
    await state.clear()
    await message.answer(f"✅ Плейлист «{title}» создан.")
    await _render_playlists(message, message.from_user, page=1, edit=False)


async def _open_playlist(callback: CallbackQuery) -> None:
    _, _, playlist_id, page = callback.data.split(":")
    if await show_playlist_view(callback, int(playlist_id), int(page)):
        await callback.answer()
    else:
        await callback.answer("Плейлист не найден", show_alert=True)


@router.callback_query(F.data.startswith("pl:open:"))
async def cb_playlist_open(callback: CallbackQuery) -> None:
    await _open_playlist(callback)


@router.callback_query(F.data.startswith("pl:page:"))
async def cb_playlist_page(callback: CallbackQuery) -> None:
    await _open_playlist(callback)


@router.callback_query(F.data.startswith("pl:delask:"))
async def cb_playlist_delete_ask(callback: CallbackQuery) -> None:
    playlist_id = int(callback.data.split(":")[2])
    async with session_factory() as session:
        user = await ensure_user(session, callback.from_user)
        playlist = await get_playlist(session, playlist_id)
        if playlist is None or playlist.user_id != user.id:
            await callback.answer("Плейлист не найден", show_alert=True)
            return
    await callback.message.edit_text(
        f"Удалить плейлист «{playlist.title}»?\n\nТреки останутся в базе и вашей библиотеке.",
        reply_markup=confirm_delete_keyboard(playlist_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("pl:del:"))
async def cb_playlist_delete(callback: CallbackQuery) -> None:
    playlist_id = int(callback.data.split(":")[2])
    async with session_factory() as session:
        user = await ensure_user(session, callback.from_user)
        playlist = await get_playlist(session, playlist_id)
        if playlist is not None and playlist.user_id == user.id:
            await delete_playlist(session, playlist_id)
    await callback.answer("Плейлист удалён")
    await _render_playlists(callback.message, callback.from_user, page=1, edit=True)

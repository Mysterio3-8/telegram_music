from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import session_factory
from app.db.models import User
from app.handlers.common import ensure_user
from app.keyboards.main_menu import main_menu_keyboard
from app.services.users import count_library_tracks, count_playlists

router = Router()


async def build_cabinet_text(session: AsyncSession, user: User) -> str:
    library_count = await count_library_tracks(session, user.id)
    playlist_count = await count_playlists(session, user.id)
    subscription = "Premium" if user.premium else "Бесплатная"
    return (
        "👋 Добро пожаловать!\n\n"
        f"Имя: {user.first_name or '—'}\n"
        f"Telegram ID: {user.telegram_id}\n\n"
        f"Подписка: {subscription}\n\n"
        f"Треков в библиотеке: {library_count}\n"
        f"Плейлистов: {playlist_count}\n\n"
        "Выберите действие:"
    )


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    async with session_factory() as session:
        user = await ensure_user(session, message.from_user)
        text = await build_cabinet_text(session, user)
    await message.answer(text, reply_markup=main_menu_keyboard())


@router.callback_query(F.data == "menu:main")
async def cb_main_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    async with session_factory() as session:
        user = await ensure_user(session, callback.from_user)
        text = await build_cabinet_text(session, user)
    await callback.message.edit_text(text, reply_markup=main_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data == "noop")
async def cb_noop(callback: CallbackQuery) -> None:
    await callback.answer()

from aiogram import F, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import session_factory
from app.db.models import User, UserLibrary
from app.handlers.cards import show_track_card
from app.handlers.common import ensure_user
from app.keyboards.main_menu import main_menu_keyboard
from app.keyboards.subscription import subscription_gate_keyboard
from app.services.gamification import register_referral
from app.services.library import get_track
from app.services.premium import is_premium_active
from app.services.subscription import is_fully_subscribed
from app.services.users import count_library_tracks, count_playlists, get_user_by_telegram_id

router = Router()

SUBSCRIPTION_GATE_TEXT = (
    "🎵 Для использования ТГ Музыки подпишитесь на наши каналы.\n\n"
    "После подписки нажмите «Проверить подписку»."
)


async def build_cabinet_text(session: AsyncSession, user: User) -> str:
    library_count = await count_library_tracks(session, user.id)
    playlist_count = await count_playlists(session, user.id)
    if is_premium_active(user) and user.premium_until is not None:
        subscription = f"Premium до {user.premium_until.strftime('%d.%m.%Y')}"
    else:
        subscription = "Бесплатная"
    return (
        "👋 Добро пожаловать!\n\n"
        f"Имя: {user.first_name or '—'}\n"
        f"Telegram ID: {user.telegram_id}\n\n"
        f"Подписка: {subscription}\n\n"
        f"Треков в библиотеке: {library_count}\n"
        f"Плейлистов: {playlist_count}\n\n"
        "Выберите действие:"
    )


async def _show_shared_track(message: Message, user: User, args: str) -> bool:
    """Обрабатывает deep-link /start track_{id}. True — карточка показана."""
    track_id_raw = args.removeprefix("track_")
    if not track_id_raw.isdigit():
        return False
    async with session_factory() as session:
        track = await get_track(session, int(track_id_raw))
        if track is None:
            return False
        in_library = await session.get(UserLibrary, (user.id, track.id)) is not None
        await show_track_card(message, session, user, track, ctx="srch", in_library=in_library)
    return True


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, command: CommandObject) -> None:
    await state.clear()
    async with session_factory() as session:
        existing = await get_user_by_telegram_id(session, message.from_user.id)
        is_new = existing is None
        user = await ensure_user(session, message.from_user)
        if is_new and command.args and command.args.startswith("ref_"):
            referrer_raw = command.args.removeprefix("ref_")
            if referrer_raw.isdigit():
                await register_referral(session, user, int(referrer_raw))
        subscribed = await is_fully_subscribed(
            session, message.bot, user.id, user.telegram_id, force=True
        )
        if not subscribed:
            from app.services.required_channels import get_required_channels

            channels = await get_required_channels(session)
            await message.answer(
                SUBSCRIPTION_GATE_TEXT, reply_markup=subscription_gate_keyboard(channels)
            )
            return
        text = await build_cabinet_text(session, user)
    if command.args and command.args.startswith("track_"):
        if await _show_shared_track(message, user, command.args):
            return
    await message.answer(text, reply_markup=main_menu_keyboard())


async def render_main_menu(callback: CallbackQuery) -> None:
    """Рисует главное меню на месте сообщения callback-а. Не answer-ит."""
    async with session_factory() as session:
        user = await ensure_user(session, callback.from_user)
        text = await build_cabinet_text(session, user)
    await callback.message.edit_text(text, reply_markup=main_menu_keyboard())


@router.callback_query(F.data == "menu:main")
async def cb_main_menu(callback: CallbackQuery, state: FSMContext) -> None:
    # set_state(None) вместо clear() — сохраняем данные поиска, чтобы пагинация
    # и «Слушать всё» в оставшихся выше сообщениях продолжали работать (доработки, п.2)
    await state.set_state(None)
    await render_main_menu(callback)
    await callback.answer()


@router.callback_query(F.data == "noop")
async def cb_noop(callback: CallbackQuery) -> None:
    await callback.answer()

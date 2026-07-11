from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from app.db.base import session_factory
from app.db.models import UserLibrary
from app.handlers.cards import show_track_card
from app.handlers.common import ensure_user
from app.keyboards.track_card import pick_playlist_keyboard
from app.services.library import add_to_library, get_track, remove_from_library
from app.services.playlists import (
    add_track_to_playlist,
    get_all_playlists,
    get_playlist,
    remove_track_from_playlist,
)

router = Router()


async def _is_in_library(session, user_id: int, track_id: int) -> bool:
    return await session.get(UserLibrary, (user_id, track_id)) is not None


@router.callback_query(F.data.startswith("trk:"))
async def cb_open_card(callback: CallbackQuery) -> None:
    _, track_id, ctx = callback.data.split(":", 2)
    async with session_factory() as session:
        user = await ensure_user(session, callback.from_user)
        track = await get_track(session, int(track_id))
        if track is None:
            await callback.answer("Трек не найден", show_alert=True)
            return
        in_library = await _is_in_library(session, user.id, track.id)
    await show_track_card(callback.message, track, ctx, in_library)
    await callback.answer()


@router.callback_query(F.data.startswith("ta:"))
async def cb_track_action(callback: CallbackQuery) -> None:
    _, action, track_id, ctx = callback.data.split(":", 3)
    track_id = int(track_id)
    async with session_factory() as session:
        user = await ensure_user(session, callback.from_user)
        track = await get_track(session, track_id)
        if track is None:
            await callback.answer("Трек не найден", show_alert=True)
            return

        if action == "addlib":
            added = await add_to_library(session, user.id, track_id)
            await callback.answer("Добавлено в библиотеку" if added else "Уже в библиотеке")
            await show_track_card(callback.message, track, ctx, in_library=True)
            return

        if action == "dellib":
            await remove_from_library(session, user.id, track_id)
            await callback.answer("Удалено из библиотеки")
            await show_track_card(callback.message, track, ctx, in_library=False)
            return

        if action == "plmenu":
            playlists = await get_all_playlists(session, user.id)
            if not playlists:
                await callback.answer(
                    "У вас пока нет плейлистов — создайте в разделе 📂 Плейлисты",
                    show_alert=True,
                )
                return
            await callback.message.edit_text(
                "Выберите плейлист:",
                reply_markup=pick_playlist_keyboard(playlists, track_id, ctx),
            )
            await callback.answer()
            return

        if action.startswith("pick_"):
            playlist = await get_playlist(session, int(action.removeprefix("pick_")))
            if playlist is None or playlist.user_id != user.id:
                await callback.answer("Плейлист не найден", show_alert=True)
                return
            added = await add_track_to_playlist(session, playlist.id, track_id)
            await callback.answer(
                f"Добавлено в «{playlist.title}»" if added else "Трек уже в этом плейлисте"
            )
            in_library = await _is_in_library(session, user.id, track_id)
            await show_track_card(callback.message, track, ctx, in_library)
            return

        if action == "delpl" and ctx.startswith("pl."):
            playlist_id = int(ctx.split(".")[1])
            playlist = await get_playlist(session, playlist_id)
            if playlist is not None and playlist.user_id == user.id:
                await remove_track_from_playlist(session, playlist_id, track_id)
            await callback.answer("Удалено из плейлиста")
            from app.handlers.playlists import show_playlist_view

            await show_playlist_view(callback, playlist_id, page=1)
            return

        if action == "share":
            me = await callback.bot.me()
            await callback.message.answer(
                f"Поделитесь треком «{track.artist} — {track.title}»:\n"
                f"https://t.me/{me.username}?start=track_{track.id}"
            )
            await callback.answer()
            return

        if action == "file":
            if track.storage_path and track.storage_path.startswith("tg://"):
                await callback.message.answer_audio(track.storage_path.removeprefix("tg://"))
                await callback.answer()
            else:
                await callback.answer(
                    "Файл будет доступен после подключения хранилища (Этап 4)", show_alert=True
                )
            return

    await callback.answer()


@router.callback_query(F.data.startswith("back:"))
async def cb_card_back(callback: CallbackQuery, state: FSMContext) -> None:
    ctx = callback.data.split(":", 1)[1]
    # Локальные импорты — back-навигация ведёт в модули, которые сами открывают карточки
    if ctx.startswith("lib."):
        from app.handlers.library import show_library_page

        await show_library_page(callback.message, callback.from_user, page=int(ctx.split(".")[1]))
    elif ctx.startswith("pl."):
        from app.handlers.playlists import show_playlist_view

        _, playlist_id, page = ctx.split(".")
        if not await show_playlist_view(callback, int(playlist_id), int(page)):
            await callback.answer("Плейлист не найден", show_alert=True)
            return
    else:  # srch — вернуться к результатам поиска
        from app.handlers.search import rerender_track_results

        if not await rerender_track_results(callback, state):
            await callback.answer("Повторите поиск — запрос устарел", show_alert=True)
            return
    await callback.answer()

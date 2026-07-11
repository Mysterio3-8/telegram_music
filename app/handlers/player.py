"""Очередь воспроизведения и режим «Микс» (SPEC: доработки, п.3 и п.9).

Telegram-клиент автоматически проигрывает следующее аудиосообщение в чате,
поэтому пачка подряд отправленных аудио = непрерывная очередь. Bot API не
сообщает об окончании прослушивания, поэтому бесконечность микса реализована
кнопкой продолжения под последним треком пачки: один тап — следующая пачка,
воспроизведение при этом не прерывается.
"""
from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.config import settings
from app.db.base import session_factory
from app.db.models import Track, User
from app.handlers.common import ensure_user
from app.handlers.delivery import send_track_audio
from app.keyboards.player import queue_continue_keyboard
from app.services.playlists import get_playlist
from app.services.queue import (
    get_library_batch,
    get_mix_batch,
    get_playlist_batch,
    get_search_batch,
)

router = Router()

MIX_RECENT_LIMIT = 50  # сколько последних треков микса не повторяем


async def _send_batch(
    callback: CallbackQuery,
    session,
    user: User,
    tracks: list[Track],
    next_callback: str | None,
    continue_label: str = "▶️ Дальше",
) -> int:
    """Отправляет пачку аудио; кнопка продолжения — под последним. Возвращает число отправленных."""
    last_message: Message | None = None
    sent = 0
    for track in tracks:
        message = await send_track_audio(
            callback.bot, callback.message.chat.id, session, user, track
        )
        if message is not None:
            sent += 1
            last_message = message
    if last_message is not None and next_callback is not None:
        try:
            await last_message.edit_reply_markup(
                reply_markup=queue_continue_keyboard(next_callback, continue_label)
            )
        except TelegramBadRequest:
            pass
    return sent


# --- Микс: бесконечное случайное радио по библиотеке ---


async def _play_mix(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    recent: list[int] = data.get("mix_recent", [])
    async with session_factory() as session:
        user = await ensure_user(session, callback.from_user)
        tracks = await get_mix_batch(session, user.id, recent)
        if not tracks:
            await callback.answer("Библиотека пуста — добавьте треки", show_alert=True)
            return
        await callback.answer("🎶 Микс запущен")
        await _send_batch(
            callback, session, user, tracks, next_callback="q:mixn",
            continue_label="🎲 Продолжить микс",
        )
    recent = (recent + [track.id for track in tracks])[-MIX_RECENT_LIMIT:]
    await state.update_data(mix_recent=recent)


@router.callback_query(F.data == "q:mix")
async def cb_mix_start(callback: CallbackQuery, state: FSMContext) -> None:
    await _play_mix(callback, state)


@router.callback_query(F.data == "q:mixn")
async def cb_mix_next(callback: CallbackQuery, state: FSMContext) -> None:
    await _play_mix(callback, state)


@router.callback_query(F.data == "lib:random")
async def cb_mix_legacy(callback: CallbackQuery, state: FSMContext) -> None:
    """Старая кнопка «Случайный трек» в уже отправленных сообщениях — теперь микс."""
    await _play_mix(callback, state)


# --- Очередь: библиотека / плейлист / результаты поиска ---


@router.callback_query(F.data.startswith("q:lib:"))
async def cb_queue_library(callback: CallbackQuery) -> None:
    offset = int(callback.data.split(":")[2])
    async with session_factory() as session:
        user = await ensure_user(session, callback.from_user)
        tracks = await get_library_batch(session, user.id, offset)
        if not tracks:
            await callback.answer(
                "Библиотека пуста" if offset == 0 else "✅ Очередь закончилась", show_alert=True
            )
            return
        await callback.answer("▶️ Включаю библиотеку")
        next_cb = f"q:lib:{offset + len(tracks)}" if len(tracks) == settings.queue_batch_size else None
        await _send_batch(callback, session, user, tracks, next_cb)


@router.callback_query(F.data.startswith("q:pl:"))
async def cb_queue_playlist(callback: CallbackQuery) -> None:
    _, _, playlist_id, offset = callback.data.split(":")
    playlist_id, offset = int(playlist_id), int(offset)
    async with session_factory() as session:
        user = await ensure_user(session, callback.from_user)
        playlist = await get_playlist(session, playlist_id)
        if playlist is None or playlist.user_id != user.id:
            await callback.answer("Плейлист не найден", show_alert=True)
            return
        tracks = await get_playlist_batch(session, playlist_id, offset)
        if not tracks:
            await callback.answer(
                "Плейлист пуст" if offset == 0 else "✅ Плейлист доигран", show_alert=True
            )
            return
        await callback.answer(f"▶️ Включаю «{playlist.title}»")
        next_cb = (
            f"q:pl:{playlist_id}:{offset + len(tracks)}"
            if len(tracks) == settings.queue_batch_size
            else None
        )
        await _send_batch(callback, session, user, tracks, next_cb)


@router.callback_query(F.data.startswith("q:srch:"))
async def cb_queue_search(callback: CallbackQuery, state: FSMContext) -> None:
    offset = int(callback.data.split(":")[2])
    data = await state.get_data()
    query = data.get("track_query")
    if not query:
        await callback.answer("Результаты устарели — выполните поиск заново", show_alert=True)
        return
    async with session_factory() as session:
        user = await ensure_user(session, callback.from_user)
        tracks = await get_search_batch(session, query, offset)
        if not tracks:
            await callback.answer(
                "Ничего не найдено" if offset == 0 else "✅ Результаты доиграны", show_alert=True
            )
            return
        await callback.answer("▶️ Включаю результаты поиска")
        next_cb = (
            f"q:srch:{offset + len(tracks)}" if len(tracks) == settings.queue_batch_size else None
        )
        await _send_batch(callback, session, user, tracks, next_cb)


@router.callback_query(F.data == "q:stop")
async def cb_queue_stop(callback: CallbackQuery) -> None:
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except TelegramBadRequest:
        pass
    await callback.answer("⏹ Очередь остановлена")

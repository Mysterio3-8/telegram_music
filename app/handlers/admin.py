"""Админ-панель (SPEC: доработки, п.6) и правка метаданных трека (п.1, п.5).

Доступ — по ADMIN_IDS из .env (Telegram ID через запятую).
"""
from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from app.db.base import session_factory
from app.handlers.cards import is_admin
from app.keyboards.admin import admin_panel_keyboard
from app.services.library import get_track, update_track_meta
from app.services.stats import ProjectStats, collect_stats

router = Router()

MAX_META_LENGTH = 256
KEEP_MARK = "-"  # ответ «-» — оставить поле без изменений


class TrackEdit(StatesGroup):
    waiting_title = State()
    waiting_artist = State()


def _stats_text(stats: ProjectStats) -> str:
    lines = [
        "📊 Статистика проекта",
        "",
        f"👥 Пользователи: {stats.users_total}",
        f"├ Новых за день: {stats.users_new_day}",
        f"├ Новых за неделю: {stats.users_new_week}",
        f"├ Активных за день: {stats.users_active_day}",
        f"├ Активных за неделю: {stats.users_active_week}",
        f"└ 💎 Premium: {stats.premium_active}",
        "",
        f"🎵 Треков в базе: {stats.tracks_total}",
        f"⬆️ Загрузок: {stats.uploads_total}",
        f"📂 Плейлистов: {stats.playlists_total}",
        "",
        f"🎧 Прослушиваний: {stats.listens_total} (за день: {stats.listens_day})",
        f"⬇️ Скачиваний: {stats.downloads_total} (за день: {stats.downloads_day})",
    ]
    if stats.top_tracks:
        lines += ["", "🔥 Популярные треки:"]
        lines += [
            f"{position}. {track.artist} — {track.title} ({plays})"
            for position, (track, plays) in enumerate(stats.top_tracks, start=1)
        ]
    return "\n".join(lines)


@router.message(Command("admin"))
async def cmd_admin(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return  # для остальных команда невидима
    async with session_factory() as session:
        stats = await collect_stats(session)
    await message.answer(_stats_text(stats), reply_markup=admin_panel_keyboard())


@router.callback_query(F.data == "adm:stats")
async def cb_admin_stats(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Недоступно", show_alert=True)
        return
    async with session_factory() as session:
        stats = await collect_stats(session)
    try:
        await callback.message.edit_text(_stats_text(stats), reply_markup=admin_panel_keyboard())
    except TelegramBadRequest:
        pass  # цифры не изменились
    await callback.answer("Обновлено")


# --- Правка метаданных трека из карточки ---


@router.callback_query(F.data.startswith("ta:edit:"))
async def cb_track_edit(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Недоступно", show_alert=True)
        return
    _, _, track_id, ctx = callback.data.split(":", 3)
    async with session_factory() as session:
        track = await get_track(session, int(track_id))
    if track is None:
        await callback.answer("Трек не найден", show_alert=True)
        return
    await state.set_state(TrackEdit.waiting_title)
    await state.update_data(edit_track_id=track.id)
    await callback.message.answer(
        f"✏️ Редактирование: {track.artist} — {track.title}\n\n"
        f"Введите новое название (или «{KEEP_MARK}», чтобы оставить текущее)."
    )
    await callback.answer()


def _clean_meta_value(text: str) -> str | None:
    """None — оставить без изменений."""
    value = text.strip()
    return None if value == KEEP_MARK else value


@router.message(TrackEdit.waiting_title, F.text)
async def process_edit_title(message: Message, state: FSMContext) -> None:
    value = _clean_meta_value(message.text)
    if value is not None and (not value or len(value) > MAX_META_LENGTH):
        await message.answer(f"Название от 1 до {MAX_META_LENGTH} символов. Попробуйте ещё раз.")
        return
    await state.update_data(edit_title=value)
    await state.set_state(TrackEdit.waiting_artist)
    await message.answer(f"Введите нового исполнителя (или «{KEEP_MARK}», чтобы оставить).")


@router.message(TrackEdit.waiting_artist, F.text)
async def process_edit_artist(message: Message, state: FSMContext) -> None:
    artist = _clean_meta_value(message.text)
    if artist is not None and (not artist or len(artist) > MAX_META_LENGTH):
        await message.answer(f"Имя исполнителя от 1 до {MAX_META_LENGTH} символов. Попробуйте ещё раз.")
        return
    data = await state.get_data()
    await state.set_state(None)
    async with session_factory() as session:
        track = await update_track_meta(
            session, data["edit_track_id"], data.get("edit_title"), artist
        )
    if track is None:
        await message.answer("Трек не найден.")
        return
    await message.answer(
        f"✅ Сохранено: {track.artist} — {track.title}\n\n"
        "Файл будет перетегирован и переименован при следующей выдаче — "
        "пользователи получат его уже с новыми данными."
    )

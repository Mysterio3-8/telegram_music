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
from app.db.models import Track
from app.services.users import is_admin
from app.keyboards.admin import admin_panel_keyboard, reclaim_confirm_keyboard
from app.services.library import get_track, update_track_meta
from app.services.recommendations import VALID_MOODS
from app.services.stats import ProjectStats, collect_stats
from app.services.storage_cleanup import reclaim_disk_space
from app.storage import get_storage

router = Router()

MAX_META_LENGTH = 256
KEEP_MARK = "-"  # ответ «-» — оставить поле без изменений


class TrackEdit(StatesGroup):
    waiting_title = State()
    waiting_artist = State()
    waiting_mood = State()


def _format_mb(size_bytes: int) -> str:
    return f"{size_bytes / (1024 * 1024):.1f} МБ"


def _stats_text(stats: ProjectStats) -> str:
    lines = [
        "📊 Статистика проекта",
        "",
        f"👥 Пользователи: {stats.users_total}",
        f"├ Новых за день: {stats.users_new_day}",
        f"├ Активных за всё время: {stats.users_active_all_time}",
        f"└ 💎 Premium: {stats.premium_active}",
        "",
        f"🎵 Треков в базе: {stats.tracks_total} — все доступны для прослушивания",
        f"📀 Из них с архивом на диске: {stats.archived_on_disk}",
    ]
    if stats.reclaimable_count > 0:
        lines.append(
            f"   └ 🧹 можно освободить: {stats.reclaimable_count} "
            f"(~{_format_mb(stats.reclaimable_bytes)}) — уже есть в Telegram"
        )
    return "\n".join(lines)


@router.message(Command("admin"))
async def cmd_admin(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return  # для остальных команда невидима
    async with session_factory() as session:
        stats = await collect_stats(session)
    await message.answer(
        _stats_text(stats), reply_markup=admin_panel_keyboard(stats.reclaimable_count)
    )


@router.callback_query(F.data == "adm:stats")
async def cb_admin_stats(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Недоступно", show_alert=True)
        return
    async with session_factory() as session:
        stats = await collect_stats(session)
    try:
        await callback.message.edit_text(
            _stats_text(stats), reply_markup=admin_panel_keyboard(stats.reclaimable_count)
        )
    except TelegramBadRequest:
        pass  # цифры не изменились
    await callback.answer("Обновлено")


# --- Очистка архивных копий с диска (уже надёжно доступны через tg_file_id) ---


@router.callback_query(F.data == "adm:reclaim:ask")
async def cb_reclaim_ask(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Недоступно", show_alert=True)
        return
    async with session_factory() as session:
        stats = await collect_stats(session)
    if stats.reclaimable_count == 0:
        await callback.answer("Нечего чистить — архивных дублей нет", show_alert=True)
        return
    await callback.message.edit_text(
        f"Удалить архивные копии {stats.reclaimable_count} треков "
        f"(~{_format_mb(stats.reclaimable_bytes)}) с диска сервера?\n\n"
        "Треки продолжат работать через Telegram (tg_file_id) — на прослушивание "
        "это не влияет. Отменить это действие нельзя.",
        reply_markup=reclaim_confirm_keyboard(stats.reclaimable_count),
    )
    await callback.answer()


@router.callback_query(F.data == "adm:reclaim:go")
async def cb_reclaim_go(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Недоступно", show_alert=True)
        return
    async with session_factory() as session:
        deleted = await reclaim_disk_space(session, get_storage())
        stats = await collect_stats(session)
    await callback.message.edit_text(
        f"✅ Удалено файлов: {deleted}\n\n{_stats_text(stats)}",
        reply_markup=admin_panel_keyboard(stats.reclaimable_count),
    )
    await callback.answer("Диск очищен")


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
    async with session_factory() as session:
        track = await update_track_meta(
            session, data["edit_track_id"], data.get("edit_title"), artist
        )
    if track is None:
        await state.set_state(None)
        await message.answer("Трек не найден.")
        return
    await state.set_state(TrackEdit.waiting_mood)
    await message.answer(
        "Настроение трека для рекомендаций?\n"
        "happy / sad / energetic / calm / love\n"
        f"(или «{KEEP_MARK}» — оставить как есть)"
    )


@router.message(TrackEdit.waiting_mood, F.text)
async def process_edit_mood(message: Message, state: FSMContext) -> None:
    raw = message.text.strip()
    data = await state.get_data()
    await state.set_state(None)
    async with session_factory() as session:
        track = await session.get(Track, data["edit_track_id"])
        if track is None:
            await message.answer("Трек не найден.")
            return
        if raw != KEEP_MARK:
            mood = raw.lower()
            if mood in VALID_MOODS:
                track.mood = mood
                await session.commit()
            else:
                await message.answer("Неизвестное настроение — оставил прежнее.")
        title, artist, current_mood = track.title, track.artist, track.mood
    await message.answer(
        f"✅ Сохранено: {artist} — {title}\n"
        f"Настроение: {current_mood or '—'}\n\n"
        "Файл будет перетегирован и переименован при следующей выдаче — "
        "пользователи получат его уже с новыми данными."
    )

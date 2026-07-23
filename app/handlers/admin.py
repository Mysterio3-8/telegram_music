"""Админ-панель (SPEC: доработки, п.6) и правка метаданных трека (п.1, п.5).

Доступ — по ADMIN_IDS из .env (Telegram ID через запятую).
"""
from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from app.config import settings
from app.db.base import session_factory
from app.db.models import Track
from app.services.users import is_admin
from app.keyboards.admin import (
    admin_panel_keyboard,
    junk_confirm_keyboard,
    reclaim_confirm_keyboard,
    sub_channels_keyboard,
)
from app.services.catalog_cleanup import count_junk_tracks, delete_junk_tracks, list_junk_tracks
from app.services.required_channels import (
    add_required_channel,
    get_required_channels,
    normalize_bot_link,
    normalize_channel,
    remove_required_channel,
)
from app.services.subscription import check_channel_membership
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


class SubChannelAdd(StatesGroup):
    waiting_channel = State()
    waiting_label = State()


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
    if stats.junk_count > 0:
        lines.append(
            f"🗑 Не похоже на музыку: {stats.junk_count} "
            f"(<{settings.track_min_seconds} сек или >{settings.track_max_seconds // 60} мин)"
        )
    return "\n".join(lines)


@router.message(Command("admin"))
async def cmd_admin(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return  # для остальных команда невидима
    async with session_factory() as session:
        stats = await collect_stats(session)
    await message.answer(
        _stats_text(stats), reply_markup=admin_panel_keyboard(stats.reclaimable_count, stats.junk_count)
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
            _stats_text(stats), reply_markup=admin_panel_keyboard(stats.reclaimable_count, stats.junk_count)
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
        reply_markup=admin_panel_keyboard(stats.reclaimable_count, stats.junk_count),
    )
    await callback.answer("Диск очищен")


# --- Каналы обязательной подписки: управление из админки (TZ §14-17) ---


def _sub_channels_text(channels) -> str:
    if not channels:
        return (
            "📢 Обязательная подписка\n\n"
            "Список пуст — гейт подписки ВЫКЛЮЧЕН, бот доступен всем без подписки."
        )
    lines = ["📢 Обязательная подписка\n"]
    lines += [
        f"{i}. {'🤖 ' if row.kind == 'bot' else ''}{row.label} — {row.channel}"
        for i, row in enumerate(channels, start=1)
    ]
    lines.append(
        "\nКаналы проверяются по подписке. Боты (🤖) — кнопкой в гейте: "
        "Telegram не даёт проверить запуск чужого бота."
    )
    return "\n".join(lines)


async def _show_sub_channels(message, session) -> None:
    channels = await get_required_channels(session)
    await message.edit_text(_sub_channels_text(channels), reply_markup=sub_channels_keyboard(channels))


@router.callback_query(F.data == "adm:subch")
async def cb_sub_channels(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Недоступно", show_alert=True)
        return
    async with session_factory() as session:
        await _show_sub_channels(callback.message, session)
    await callback.answer()


@router.callback_query(F.data.startswith("adm:subch:del:"))
async def cb_sub_channel_delete(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Недоступно", show_alert=True)
        return
    channel_id = int(callback.data.rsplit(":", 1)[1])
    async with session_factory() as session:
        removed = await remove_required_channel(session, channel_id)
        await _show_sub_channels(callback.message, session)
    await callback.answer("Канал убран" if removed else "Уже удалён")


@router.callback_query(F.data == "adm:subch:add")
async def cb_sub_channel_add(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Недоступно", show_alert=True)
        return
    await state.set_state(SubChannelAdd.waiting_channel)
    await callback.message.answer(
        "Пришлите канал или бота:\n"
        "• канал — @username или id вида -100…\n"
        "• бот (ОП на ботов) — ссылка t.me/ИмяBot (можно с ?start=…)\n\n"
        "⚠️ Для канала бот должен быть его админом — иначе Telegram не даёт проверять подписку.\n"
        "🤖 Запуск чужого бота проверить нельзя — он попадёт в гейт кнопкой без проверки."
    )
    await callback.answer()


@router.message(SubChannelAdd.waiting_channel, F.text)
async def process_sub_channel(message: Message, state: FSMContext) -> None:
    # «ОП на ботов»: ссылка на бота — отдельная ветка без проверки членства
    bot_link = normalize_bot_link(message.text)
    if bot_link is not None:
        await state.update_data(new_channel=bot_link, new_kind="bot")
        await state.set_state(SubChannelAdd.waiting_label)
        await message.answer("🤖 Бот принят. Текст кнопки для гейта (например «🤖 Запусти бота»):")
        return

    channel = normalize_channel(message.text)
    if channel is None:
        await message.answer(
            "Не похоже ни на канал, ни на бота.\n"
            "Канал: @username или -100XXXXXXXXXX. Бот: ссылка t.me/ИмяBot."
        )
        return
    # Живая проверка тем же вызовом, которым работает гейт: если getChatMember
    # не отвечает — бот не админ канала, и подписку проверить не сможет
    if not await check_channel_membership(message.bot, message.from_user.id, channel):
        await message.answer(
            f"Не могу проверить участников {channel}.\n"
            "Убедитесь, что канал существует, бот добавлен в него админом, "
            "а вы сами на него подписаны, — и пришлите канал ещё раз."
        )
        return
    await state.update_data(new_channel=channel, new_kind="channel")
    await state.set_state(SubChannelAdd.waiting_label)
    await message.answer("Текст кнопки для гейта (например «📢 ТГ Музыка»):")


@router.message(SubChannelAdd.waiting_label, F.text)
async def process_sub_channel_label(message: Message, state: FSMContext) -> None:
    label = message.text.strip()
    if not label or len(label) > 128:
        await message.answer("Текст кнопки от 1 до 128 символов. Попробуйте ещё раз.")
        return
    data = await state.get_data()
    await state.set_state(None)
    async with session_factory() as session:
        row = await add_required_channel(
            session, data["new_channel"], label, kind=data.get("new_kind", "channel")
        )
        channels = await get_required_channels(session)
    if row is None:
        await message.answer("Такой канал/бот уже в списке.")
        return
    await message.answer(
        f"✅ Добавлен: {label} — {row.channel}\n\n{_sub_channels_text(channels)}",
        reply_markup=sub_channels_keyboard(channels),
    )


# --- Очистка не-музыки (короче/длиннее музыкальных границ) — удаляет НАВСЕГДА ---


@router.callback_query(F.data == "adm:junk:ask")
async def cb_junk_ask(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Недоступно", show_alert=True)
        return
    async with session_factory() as session:
        junk = await count_junk_tracks(session)
        preview = await list_junk_tracks(session)
    if junk.count == 0:
        await callback.answer("Мусора нет — все треки в музыкальных границах", show_alert=True)
        return
    sample = "\n".join(
        f"• {t.artist} — {t.title} ({t.duration // 60}:{t.duration % 60:02d})" for t in preview
    )
    more = f"\n…и ещё {junk.count - len(preview)}" if junk.count > len(preview) else ""
    await callback.message.edit_text(
        f"Найдено {junk.count} треков, не похожих на музыку "
        f"(<{settings.track_min_seconds} сек или >{settings.track_max_seconds // 60} мин), "
        f"~{_format_mb(junk.total_bytes)} в файлах:\n\n{sample}{more}\n\n"
        "⚠️ Удаляются НАВСЕГДА: файлы, записи, связи с библиотеками и плейлистами. "
        "Отменить нельзя.",
        reply_markup=junk_confirm_keyboard(junk.count),
    )
    await callback.answer()


@router.callback_query(F.data == "adm:junk:go")
async def cb_junk_go(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Недоступно", show_alert=True)
        return
    async with session_factory() as session:
        deleted = await delete_junk_tracks(session, get_storage())
        stats = await collect_stats(session)
    await callback.message.edit_text(
        f"✅ Удалено треков: {deleted}\n\n{_stats_text(stats)}",
        reply_markup=admin_panel_keyboard(stats.reclaimable_count, stats.junk_count),
    )
    await callback.answer("База очищена")


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

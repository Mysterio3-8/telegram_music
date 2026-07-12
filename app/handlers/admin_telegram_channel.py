"""Управление импортом из личного Telegram-канала — из админ-панели."""
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from app.db.base import session_factory
from app.db.models import TelegramChannelSource
from app.handlers.cards import is_admin
from app.keyboards.admin_telegram_channel import (
    confirm_delete_keyboard,
    source_view_keyboard,
    sources_keyboard,
)
from app.services.app_settings import (
    TELEGRAM_CHANNEL_IMPORT_ENABLED,
    is_telegram_channel_enabled,
    set_flag,
)
from app.services.telegram_channel.client import is_configured
from app.services.telegram_channel.sources import (
    add_source,
    delete_source,
    get_source,
    list_sources,
    set_source_status,
)
from app.tasks.telegram_channel import telegram_channel_scan_source

router = Router()

MAX_CHANNEL_LENGTH = 256


class TelegramChannelAdd(StatesGroup):
    waiting_channel = State()


def _sources_text(count: int, importer_enabled: bool) -> str:
    state = "🟢 импортёр включён" if importer_enabled else "🔴 импортёр выключен"
    warning = "" if is_configured() else "\n\n⚠️ Не настроен вход (см. деплой) — источники не будут импортироваться."
    if count == 0:
        return (
            f"📡 Мой Telegram-канал · {state}\n\n"
            "Пока не добавлено ни одного канала.\n"
            "«➕ Добавить канал» — пришлёте @username/ссылку, импорт запустится сам. "
            "Файлы не хранятся на сервере — только tg_file_id."
            f"{warning}"
        )
    return f"📡 Мой Telegram-канал · {state}\n\nВсего: {count}\nФормат: импортировано / найдено{warning}"


def _source_text(source: TelegramChannelSource) -> str:
    checked = source.last_checked_at.strftime("%d.%m.%Y %H:%M") if source.last_checked_at else "—"
    return (
        f"📡 Источник #{source.id}\n\n"
        f"Канал: {source.channel}\n"
        f"Статус: {'активен' if source.status == 'active' else 'отключён'}\n"
        f"Найдено постов с аудио: {source.found_count}\n"
        f"Импортировано треков: {source.imported_count}\n"
        f"Последняя проверка: {checked}"
    )


async def _guard(callback: CallbackQuery) -> bool:
    if not is_admin(callback.from_user.id):
        await callback.answer("Недоступно", show_alert=True)
        return False
    return True


@router.callback_query(F.data == "adm:tgc")
async def cb_sources(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _guard(callback):
        return
    await state.set_state(None)
    async with session_factory() as session:
        sources = await list_sources(session)
        enabled = await is_telegram_channel_enabled(session)
    await callback.message.edit_text(
        _sources_text(len(sources), enabled),
        reply_markup=sources_keyboard(sources, enabled),
    )
    await callback.answer()


@router.callback_query(F.data == "adm:tgc:power")
async def cb_power_toggle(callback: CallbackQuery) -> None:
    if not await _guard(callback):
        return
    async with session_factory() as session:
        enabled = await is_telegram_channel_enabled(session)
        await set_flag(session, TELEGRAM_CHANNEL_IMPORT_ENABLED, not enabled)
        sources = await list_sources(session)
        new_state = not enabled
    await callback.message.edit_text(
        _sources_text(len(sources), new_state),
        reply_markup=sources_keyboard(sources, new_state),
    )
    await callback.answer("Импортёр включён" if new_state else "Импортёр выключен")


@router.callback_query(F.data.startswith("adm:tgcs:"))
async def cb_source_view(callback: CallbackQuery) -> None:
    if not await _guard(callback):
        return
    source_id = int(callback.data.split(":")[2])
    async with session_factory() as session:
        source = await get_source(session, source_id)
    if source is None:
        await callback.answer("Источник не найден", show_alert=True)
        return
    await callback.message.edit_text(_source_text(source), reply_markup=source_view_keyboard(source))
    await callback.answer()


@router.callback_query(F.data == "adm:tgc:add")
async def cb_add_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _guard(callback):
        return
    await state.set_state(TelegramChannelAdd.waiting_channel)
    await callback.message.answer(
        "Пришлите @username канала, ссылку на него или id.\n"
        "Импорт запустится автоматически, файлы не сохраняются на сервере."
    )
    await callback.answer()


@router.message(TelegramChannelAdd.waiting_channel, F.text)
async def process_add_channel(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    channel = message.text.strip()
    if not channel or len(channel) > MAX_CHANNEL_LENGTH:
        await message.answer("Похоже, это не похоже на канал. Пришлите @username, ссылку или id.")
        return
    await state.set_state(None)
    async with session_factory() as session:
        source = await add_source(session, channel)
    telegram_channel_scan_source.delay(source_id=source.id)
    await message.answer(
        f"✅ Источник #{source.id} добавлен. Сканирую канал и ставлю треки в очередь — "
        "импорт идёт в фоне, можно продолжать пользоваться ботом."
    )


@router.callback_query(F.data.startswith("adm:tgc:scan:"))
async def cb_scan(callback: CallbackQuery) -> None:
    if not await _guard(callback):
        return
    source_id = int(callback.data.split(":")[3])
    telegram_channel_scan_source.delay(source_id=source_id)
    await callback.answer("Проверка запущена в фоне", show_alert=True)


@router.callback_query(F.data.startswith("adm:tgc:tgl:"))
async def cb_toggle(callback: CallbackQuery) -> None:
    if not await _guard(callback):
        return
    source_id = int(callback.data.split(":")[3])
    async with session_factory() as session:
        source = await get_source(session, source_id)
        if source is None:
            await callback.answer("Источник не найден", show_alert=True)
            return
        new_status = "disabled" if source.status == "active" else "active"
        await set_source_status(session, source_id, new_status)
        source = await get_source(session, source_id)
    await callback.message.edit_text(_source_text(source), reply_markup=source_view_keyboard(source))
    await callback.answer("Статус обновлён")


@router.callback_query(F.data.startswith("adm:tgc:delask:"))
async def cb_delete_ask(callback: CallbackQuery) -> None:
    if not await _guard(callback):
        return
    source_id = int(callback.data.split(":")[3])
    await callback.message.edit_text(
        "Удалить источник? Уже импортированные треки останутся в базе.",
        reply_markup=confirm_delete_keyboard(source_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:tgc:del:"))
async def cb_delete(callback: CallbackQuery) -> None:
    if not await _guard(callback):
        return
    source_id = int(callback.data.split(":")[3])
    async with session_factory() as session:
        await delete_source(session, source_id)
        sources = await list_sources(session)
        enabled = await is_telegram_channel_enabled(session)
    await callback.message.edit_text(
        _sources_text(len(sources), enabled),
        reply_markup=sources_keyboard(sources, enabled),
    )
    await callback.answer("Источник удалён")

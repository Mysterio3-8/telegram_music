"""Загрузка минусов из админ-панели (TZ §11) — отдельный визард от загрузки треков,
пишет в Instrumental, дедуп только среди минусов."""
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.handlers.common import format_duration
from app.services.instrumentals import create_admin_instrumental, find_duplicate_instrumental
from app.services.soundcloud import extract_soundcloud_url
from app.services.uploads import AudioMeta, validate_audio
from app.services.users import is_admin
from app.db.base import session_factory

router = Router()

MAX_TITLE_LENGTH = 256


class UploadMinus(StatesGroup):
    waiting_file = State()
    waiting_title = State()
    waiting_artist = State()
    waiting_confirm = State()


def _cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="admin_min:cancel")]]
    )


def _confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Загрузить", callback_data="admin_min:confirm")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_min:cancel")],
        ]
    )


def _admin_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="◀️ В админку", callback_data="adm:stats")]]
    )


@router.callback_query(F.data == "adm:upload_minus")
async def cb_upload_minus_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Недоступно", show_alert=True)
        return
    await state.set_state(UploadMinus.waiting_file)
    await callback.message.answer(
        "Отправьте аудиофайл минуса или ссылку на SoundCloud "
        "(трек, профиль или сет — заберём всё, что музыка).",
        reply_markup=_cancel_keyboard(),
    )
    await callback.answer()


@router.message(UploadMinus.waiting_file, F.audio)
async def process_minus_audio(message: Message, state: FSMContext) -> None:
    audio = message.audio
    meta = AudioMeta(
        file_id=audio.file_id,
        file_name=audio.file_name,
        mime_type=audio.mime_type,
        file_size=audio.file_size,
        duration=audio.duration or 0,
    )
    error = validate_audio(meta)
    if error:
        await message.answer(error, reply_markup=_cancel_keyboard())
        return
    await state.update_data(
        file_id=meta.file_id,
        file_name=meta.file_name,
        mime_type=meta.mime_type,
        file_size=meta.file_size,
        duration=meta.duration,
    )
    await state.set_state(UploadMinus.waiting_title)
    await message.answer("Введите название.", reply_markup=_cancel_keyboard())


@router.message(UploadMinus.waiting_file, F.text)
async def process_minus_link(message: Message, state: FSMContext) -> None:
    """Ссылка на SoundCloud → постоянный источник с автопроверкой новых битов."""
    url = extract_soundcloud_url(message.text or "")
    if url is None:
        await message.answer(
            "Жду аудиофайл или ссылку на SoundCloud 🎼", reply_markup=_cancel_keyboard()
        )
        return
    from app.services.soundcloud_sources import add_source
    from app.tasks.youtube import soundcloud_scan_source

    async with session_factory() as session:
        source, created = await add_source(session, url)
    try:
        soundcloud_scan_source.delay(source_id=source.id, chat_id=message.chat.id)
    except Exception:  # noqa: BLE001 — брокер недоступен: честно говорим, без падения бота
        await message.answer(
            "Источник сохранён, но фоновая очередь недоступна — импорт запустится "
            "при ближайшей автопроверке.",
            reply_markup=_admin_menu_keyboard(),
        )
        await state.clear()
        return
    await state.clear()
    note = "добавил как источник" if created else "источник уже был — перепроверяю"
    await message.answer(
        f"✅ Принял ссылку, {note}. Импорт идёт в фоне — пришлю отчёт.\n"
        "Новые биты с этой страницы будут подтягиваться автоматически каждый день.",
        reply_markup=_admin_menu_keyboard(),
    )


@router.message(UploadMinus.waiting_file)
async def process_minus_not_audio(message: Message) -> None:
    await message.answer(
        "Жду аудиофайл или ссылку на SoundCloud 🎼", reply_markup=_cancel_keyboard()
    )


@router.message(UploadMinus.waiting_title, F.text)
async def process_minus_title(message: Message, state: FSMContext) -> None:
    title = message.text.strip()
    if not title or len(title) > MAX_TITLE_LENGTH:
        await message.answer("Название от 1 до 256 символов. Попробуйте ещё раз.")
        return
    await state.update_data(title=title)
    await state.set_state(UploadMinus.waiting_artist)
    await message.answer("Введите исполнителя.", reply_markup=_cancel_keyboard())


@router.message(UploadMinus.waiting_artist, F.text)
async def process_minus_artist(message: Message, state: FSMContext) -> None:
    artist = message.text.strip()
    if not artist or len(artist) > MAX_TITLE_LENGTH:
        await message.answer("Имя исполнителя от 1 до 256 символов. Попробуйте ещё раз.")
        return
    await state.update_data(artist=artist)
    await state.set_state(UploadMinus.waiting_confirm)
    data = await state.get_data()
    await message.answer(
        "Проверьте данные минуса:\n\n"
        f"Название: {data['title']}\n"
        f"Исполнитель: {artist}\n"
        f"Длительность: {format_duration(data['duration'])}",
        reply_markup=_confirm_keyboard(),
    )


@router.callback_query(UploadMinus.waiting_confirm, F.data == "admin_min:confirm")
async def cb_upload_minus_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    meta = AudioMeta(
        file_id=data["file_id"],
        file_name=data.get("file_name"),
        mime_type=data.get("mime_type"),
        file_size=data.get("file_size"),
        duration=data["duration"],
    )
    async with session_factory() as session:
        duplicate = await find_duplicate_instrumental(session, data["title"], data["artist"], meta.duration)
        if duplicate is not None:
            await state.clear()
            await callback.message.edit_text(
                f"Такой минус уже есть в базе:\n{duplicate.artist} — {duplicate.title}",
                reply_markup=_admin_menu_keyboard(),
            )
            await callback.answer()
            return
        instrumental = await create_admin_instrumental(session, meta, data["title"], data["artist"])
    await state.clear()
    await callback.message.edit_text(
        f"✅ Минус «{instrumental.artist} — {instrumental.title}» добавлен в базу.",
        reply_markup=_admin_menu_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "admin_min:cancel")
async def cb_upload_minus_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("Загрузка минуса отменена.", reply_markup=_admin_menu_keyboard())
    await callback.answer()

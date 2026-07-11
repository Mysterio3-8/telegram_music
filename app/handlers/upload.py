from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.db.base import session_factory
from app.handlers.common import ensure_user, format_duration
from app.services.library import add_to_library
from app.services.uploads import AudioMeta, create_uploaded_track, find_duplicate, validate_audio

router = Router()

MAX_TITLE_LENGTH = 256


class UploadTrack(StatesGroup):
    waiting_file = State()
    waiting_title = State()
    waiting_artist = State()
    waiting_confirm = State()


def _cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="up:cancel")]]
    )


def _confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Загрузить", callback_data="up:confirm")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="up:cancel")],
        ]
    )


def _duplicate_keyboard(track_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Да, добавить", callback_data=f"up:dup:{track_id}")],
            [InlineKeyboardButton(text="❌ Нет", callback_data="up:cancel")],
        ]
    )


def _menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="◀️ В меню", callback_data="menu:main")]]
    )


@router.callback_query(F.data == "menu:upload")
async def cb_upload(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(UploadTrack.waiting_file)
    await callback.message.answer("Отправьте аудиофайл.", reply_markup=_cancel_keyboard())
    await callback.answer()


@router.message(UploadTrack.waiting_file, F.audio)
async def process_audio(message: Message, state: FSMContext) -> None:
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
    await state.set_state(UploadTrack.waiting_title)
    await message.answer("Введите название.", reply_markup=_cancel_keyboard())


@router.message(UploadTrack.waiting_file, F.document)
async def process_document(message: Message) -> None:
    await message.answer(
        "Отправьте файл как аудио (музыку), а не как документ.",
        reply_markup=_cancel_keyboard(),
    )


@router.message(UploadTrack.waiting_file)
async def process_not_audio(message: Message) -> None:
    await message.answer("Жду аудиофайл 🎵", reply_markup=_cancel_keyboard())


@router.message(UploadTrack.waiting_title, F.text)
async def process_title(message: Message, state: FSMContext) -> None:
    title = message.text.strip()
    if not title or len(title) > MAX_TITLE_LENGTH:
        await message.answer("Название от 1 до 256 символов. Попробуйте ещё раз.")
        return
    await state.update_data(title=title)
    await state.set_state(UploadTrack.waiting_artist)
    await message.answer("Введите исполнителя.", reply_markup=_cancel_keyboard())


@router.message(UploadTrack.waiting_artist, F.text)
async def process_artist(message: Message, state: FSMContext) -> None:
    artist = message.text.strip()
    if not artist or len(artist) > MAX_TITLE_LENGTH:
        await message.answer("Имя исполнителя от 1 до 256 символов. Попробуйте ещё раз.")
        return
    await state.update_data(artist=artist)
    await state.set_state(UploadTrack.waiting_confirm)
    data = await state.get_data()
    await message.answer(
        "Проверьте данные:\n\n"
        f"Название: {data['title']}\n"
        f"Исполнитель: {artist}\n"
        f"Длительность: {format_duration(data['duration'])}",
        reply_markup=_confirm_keyboard(),
    )


@router.callback_query(UploadTrack.waiting_confirm, F.data == "up:confirm")
async def cb_upload_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    meta = AudioMeta(
        file_id=data["file_id"],
        file_name=data.get("file_name"),
        mime_type=data.get("mime_type"),
        file_size=data.get("file_size"),
        duration=data["duration"],
    )
    async with session_factory() as session:
        user = await ensure_user(session, callback.from_user)
        duplicate = await find_duplicate(session, data["title"], data["artist"], meta.duration)
        if duplicate is not None:
            await state.clear()
            await callback.message.edit_text(
                f"Такой трек уже есть:\n{duplicate.artist} — {duplicate.title}\n\n"
                "Добавить его в вашу библиотеку?",
                reply_markup=_duplicate_keyboard(duplicate.id),
            )
            await callback.answer()
            return
        track = await create_uploaded_track(session, user.id, meta, data["title"], data["artist"])
    await state.clear()
    await callback.message.edit_text(
        f"✅ Трек «{track.artist} — {track.title}» добавлен в общую базу и вашу библиотеку.",
        reply_markup=_menu_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("up:dup:"))
async def cb_duplicate_add(callback: CallbackQuery) -> None:
    track_id = int(callback.data.split(":")[2])
    async with session_factory() as session:
        user = await ensure_user(session, callback.from_user)
        added = await add_to_library(session, user.id, track_id)
    await callback.message.edit_text(
        "✅ Трек добавлен в вашу библиотеку." if added else "Трек уже был в вашей библиотеке.",
        reply_markup=_menu_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "up:cancel")
async def cb_upload_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("Загрузка отменена.", reply_markup=_menu_keyboard())
    await callback.answer()

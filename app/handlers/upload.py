import asyncio

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.db.base import session_factory
from app.handlers.common import ensure_user, format_duration
from app.config import settings
from app.services.premium import is_premium_active
from app.services.soundcloud import is_soundcloud_link, normalize_soundcloud_url, soundcloud_link_kind
from app.services.uploads import AudioMeta, create_uploaded_track, find_duplicate, validate_audio
from app.services.youtube.user_import import duration_error, extract_video_id, is_playlist_link
from app.tasks import enqueue_enrich, enqueue_soundcloud_user_import, enqueue_user_import
from app.i18n import t

router = Router()

MAX_TITLE_LENGTH = 256


class UploadTrack(StatesGroup):
    waiting_file = State()
    waiting_title = State()
    waiting_artist = State()
    waiting_confirm = State()


def _cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=t("common.back_menu_long"), callback_data="up:cancel")]]
    )


def _confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t("upload.confirm_button"), callback_data="up:confirm")],
            [InlineKeyboardButton(text=t("common.back_menu_long"), callback_data="up:cancel")],
        ]
    )


def _menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=t("common.back_to_menu"), callback_data="menu:main")]]
    )


@router.callback_query(F.data == "menu:upload")
async def cb_upload(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(UploadTrack.waiting_file)
    await callback.message.answer(
        t("upload.intro"),
        parse_mode="HTML",
        reply_markup=_cancel_keyboard(),
    )
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
    await message.answer(t("upload.enter_title"), reply_markup=_cancel_keyboard())


@router.message(UploadTrack.waiting_file, F.document)
async def process_document(message: Message) -> None:
    await message.answer(
        t("upload.as_audio"),
        reply_markup=_cancel_keyboard(),
    )


async def _require_premium_for_bulk(message: Message) -> bool:
    """True — пользователь Premium (пачка разрешена). Иначе сообщает и возвращает False."""
    async with session_factory() as session:
        user = await ensure_user(session, message.from_user)
        if is_premium_active(user):
            return True
    await message.answer(
        t("upload.premium_bulk"),
        reply_markup=_cancel_keyboard(),
    )
    return False


async def _process_playlist_link(message: Message, state: FSMContext) -> None:
    """Импорт YouTube-плейлиста/канала целиком — только Premium (тихо в библиотеку)."""
    if not await _require_premium_for_bulk(message):
        return

    scanning = await message.answer(t("upload.reading_playlist"))
    from app.services.youtube.downloader import list_videos

    try:
        videos = await asyncio.to_thread(list_videos, message.text.strip())
    except Exception:  # noqa: BLE001 — yt-dlp не смог открыть источник
        videos = []
    if not videos:
        await scanning.edit_text(
            t("upload.playlist_failed"),
            reply_markup=_cancel_keyboard(),
        )
        return

    batch = videos[: settings.playlist_import_limit] if settings.playlist_import_limit else videos
    queued = sum(
        enqueue_user_import(v.video_id, message.from_user.id, message.chat.id, quiet=True)
        for v in batch
    )
    if queued == 0:
        await scanning.edit_text(
            t("upload.unavailable"), reply_markup=_menu_keyboard()
        )
        return
    await state.clear()
    await scanning.edit_text(
        t("upload.queued_videos", queued=queued),
        reply_markup=_menu_keyboard(),
    )


async def _process_soundcloud_bulk(message: Message, state: FSMContext, url: str) -> None:
    """Импорт профиля/лайков/плейлиста/поиска SoundCloud целиком — только Premium."""
    if not await _require_premium_for_bulk(message):
        return

    scanning = await message.answer(t("upload.reading_soundcloud"))
    from app.services.soundcloud import list_soundcloud_entries

    try:
        entries = await asyncio.to_thread(list_soundcloud_entries, url)
    except Exception:  # noqa: BLE001
        entries = []
    if not entries:
        await scanning.edit_text(
            t("upload.soundcloud_failed"),
            reply_markup=_cancel_keyboard(),
        )
        return

    batch = entries[: settings.playlist_import_limit] if settings.playlist_import_limit else entries
    queued = sum(
        enqueue_soundcloud_user_import(e.url, message.from_user.id, message.chat.id, quiet=True)
        for e in batch
    )
    if queued == 0:
        await scanning.edit_text(
            t("upload.unavailable"), reply_markup=_menu_keyboard()
        )
        return
    await state.clear()
    await scanning.edit_text(
        t("upload.queued_soundcloud", queued=queued),
        reply_markup=_menu_keyboard(),
    )


async def _process_soundcloud_track(message: Message, state: FSMContext, url: str) -> None:
    """Один трек SoundCloud — бесплатно."""
    if not enqueue_soundcloud_user_import(normalize_soundcloud_url(url), message.from_user.id, message.chat.id):
        await message.answer(
            t("upload.unavailable"), reply_markup=_menu_keyboard()
        )
        return
    await state.clear()
    await message.answer(
        t("upload.queued_one_soundcloud"),
        reply_markup=_menu_keyboard(),
    )


@router.message(UploadTrack.waiting_file, F.text)
async def process_link(message: Message, state: FSMContext) -> None:
    """Импорт по ссылке: YouTube Music / SoundCloud. Один трек — бесплатно,
    профиль/плейлист/лайки целиком — Premium."""
    text = message.text.strip()

    # SoundCloud: определяем одиночный трек (бесплатно) vs пачку (Premium)
    if is_soundcloud_link(text):
        kind = soundcloud_link_kind(text)
        if kind == "track":
            await _process_soundcloud_track(message, state, text)
        else:
            await _process_soundcloud_bulk(message, state, text)
        return

    video_id = extract_video_id(text)
    if video_id is None:
        if is_playlist_link(text):
            await _process_playlist_link(message, state)
            return
        await message.answer(
            t("upload.waiting_file"),
            reply_markup=_cancel_keyboard(),
        )
        return

    checking = await message.answer(t("upload.checking_link"))
    from app.services.youtube.downloader import fetch_video_info

    try:
        info = await asyncio.to_thread(fetch_video_info, video_id)
    except Exception:  # noqa: BLE001 — yt-dlp не смог открыть видео
        info = None
    if info is None:
        await checking.edit_text(
            t("upload.video_failed"),
            reply_markup=_cancel_keyboard(),
        )
        return
    if info.is_live:
        await checking.edit_text(
            t("upload.live_stream"), reply_markup=_cancel_keyboard()
        )
        return
    error = duration_error(info.duration)
    if error:
        await checking.edit_text(f"❌ {error}", reply_markup=_cancel_keyboard())
        return

    if not enqueue_user_import(video_id, message.from_user.id, message.chat.id):
        await checking.edit_text(
            t("upload.unavailable"), reply_markup=_menu_keyboard()
        )
        return
    await state.clear()
    await checking.edit_text(
        t("upload.queued_video", title=info.title, duration=format_duration(info.duration)),
        reply_markup=_menu_keyboard(),
    )


@router.message(UploadTrack.waiting_file)
async def process_not_audio(message: Message) -> None:
    await message.answer(
        t("upload.waiting_file"),
        reply_markup=_cancel_keyboard(),
    )


@router.message(UploadTrack.waiting_title, F.text)
async def process_title(message: Message, state: FSMContext) -> None:
    title = message.text.strip()
    if not title or len(title) > MAX_TITLE_LENGTH:
        await message.answer(t("upload.title_length"))
        return
    await state.update_data(title=title)
    await state.set_state(UploadTrack.waiting_artist)
    await message.answer(t("upload.enter_artist"), reply_markup=_cancel_keyboard())


@router.message(UploadTrack.waiting_artist, F.text)
async def process_artist(message: Message, state: FSMContext) -> None:
    artist = message.text.strip()
    if not artist or len(artist) > MAX_TITLE_LENGTH:
        await message.answer(t("upload.artist_length"))
        return
    await state.update_data(artist=artist)
    await state.set_state(UploadTrack.waiting_confirm)
    data = await state.get_data()

    # Мягкий антидубль (решение владельца): предупреждаем, но не блокируем — можно
    # залить вариант, поменяв название («Rex», «без цензуры»). Регистр учитывается
    # текстом: одинаковое название по буквам считаем совпадением, разное — новый трек.
    async with session_factory() as session:
        existing = await find_duplicate(session, data["title"], artist, data["duration"])
    warning = ""
    if existing is not None:
        warning = t("upload.duplicate_warning", artist=existing.artist, title=existing.title)

    await message.answer(
        t(
            "upload.check_data",
            title=data["title"],
            artist=artist,
            duration=format_duration(data["duration"]),
        )
        + warning,
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
        # Загрузка аудиофайлом — без ограничений: без счётчика и без блокировки
        # дубликатов (решение владельца), принимаем всё, что прислали
        track = await create_uploaded_track(session, user.id, meta, data["title"], data["artist"])
    enqueue_enrich(track.id, meta.file_id)
    await state.clear()
    if track.moderation_status == "pending":
        # Стоп-слово в названии — трек в вашей библиотеке, но в общий каталог
        # попадёт после проверки модератором (блок D)
        text = t("upload.moderation", artist=track.artist, title=track.title)
    else:
        text = t("upload.done", artist=track.artist, title=track.title)
    await callback.message.edit_text(text, reply_markup=_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data == "up:cancel")
async def cb_upload_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    """Выход из мастера сразу в меню (решение владельца): промежуточный экран
    «Загрузка отменена» требовал лишнего тапа и ничего не сообщал."""
    from app.handlers.start import render_main_menu

    await state.clear()
    await render_main_menu(callback)
    await callback.answer()

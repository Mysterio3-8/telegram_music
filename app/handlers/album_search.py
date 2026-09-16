"""Экран альбома в боте (16.09): открыть найденный альбом, взять трек, скачать весь.

Альбомы показываются под выдачей быстрого поиска (quick_search). Здесь — всё, что
происходит после нажатия на альбом. Решения владельца: треки по одному —
бесплатно всем, альбом целиком — с Premium.

Хендлер не качает сам: список треков берёт сервис, выдачу одного трека —
общая `deliver_candidate`, выкачку альбома — задача воркера.
"""
import asyncio
import logging
from dataclasses import asdict

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from app.db.base import session_factory
from app.handlers.common import ensure_user
from app.handlers.quick_search import deliver_candidate, stored_albums
from app.i18n import t
from app.keyboards.albums import album_keyboard, premium_offer_keyboard
from app.keyboards.albums import total_pages as album_pages
from app.services.albums import (
    AlbumCandidate,
    acquire_album_lock,
    album_tracks,
    estimate_minutes,
    release_album_lock,
)
from app.services.premium import is_premium_active
from app.services.track_lookup.ranking import Candidate

logger = logging.getLogger(__name__)

router = Router()

_ALBUM_KEY = "al_album"
_TRACKS_KEY = "al_tracks"


async def _stored_album(state: FSMContext) -> tuple[AlbumCandidate | None, list[Candidate]]:
    data = await state.get_data()
    album = data.get(_ALBUM_KEY)
    tracks = [Candidate(**row) for row in data.get(_TRACKS_KEY) or []]
    return (AlbumCandidate(**album) if album else None), tracks


def _header(album: AlbumCandidate, tracks: list[Candidate]) -> str:
    return t("album.header", artist=album.artist, title=album.title, count=len(tracks))


@router.callback_query(F.data.startswith("al:o:"))
async def open_album(callback: CallbackQuery, state: FSMContext) -> None:
    index = int(callback.data.split(":")[2])
    albums = await stored_albums(state)
    if index >= len(albums):
        await callback.answer(t("quick.stale"), show_alert=True)
        return
    album = albums[index]
    await callback.answer(t("album.loading"))
    try:
        tracks = await asyncio.to_thread(album_tracks, album.id)
    except Exception:  # noqa: BLE001 — источник лёг: честно говорим, а не молчим
        logger.warning("Альбом %s не открылся", album.id, exc_info=True)
        tracks = []
    if not tracks:
        await callback.message.answer(t("album.empty"))
        return
    await state.update_data(**{_ALBUM_KEY: album.as_dict(), _TRACKS_KEY: [asdict(c) for c in tracks]})
    await callback.message.edit_text(_header(album, tracks), reply_markup=album_keyboard(tracks, page=1))


@router.callback_query(F.data.startswith("al:p:"))
async def album_page(callback: CallbackQuery, state: FSMContext) -> None:
    album, tracks = await _stored_album(state)
    if album is None or not tracks:
        await callback.answer(t("quick.stale"), show_alert=True)
        return
    page = max(1, min(int(callback.data.split(":")[2]), album_pages(tracks)))
    try:
        await callback.message.edit_text(_header(album, tracks), reply_markup=album_keyboard(tracks, page))
    except TelegramBadRequest:
        pass  # тот же экран — Telegram отказывает в «правке без изменений»
    await callback.answer()


@router.callback_query(F.data.startswith("al:t:"))
async def album_track(callback: CallbackQuery, state: FSMContext) -> None:
    index = int(callback.data.split(":")[2])
    _, tracks = await _stored_album(state)
    if index >= len(tracks):
        await callback.answer(t("quick.stale"), show_alert=True)
        return
    await deliver_candidate(callback, tracks[index])


@router.callback_query(F.data == "al:all")
async def album_download_all(callback: CallbackQuery, state: FSMContext) -> None:
    album, tracks = await _stored_album(state)
    if album is None or not tracks:
        await callback.answer(t("quick.stale"), show_alert=True)
        return
    async with session_factory() as session:
        user = await ensure_user(session, callback.from_user)
    if not is_premium_active(user):
        await callback.answer(t("album.premium_only"), show_alert=True)
        await callback.message.answer(t("album.premium_only"), reply_markup=premium_offer_keyboard())
        return
    if not acquire_album_lock(user.telegram_id):
        await callback.answer(t("album.already"), show_alert=True)
        return
    try:
        from app.tasks.album_fetch import album_fetch_all

        album_fetch_all.delay(
            album=album.as_dict(),
            tracks=[asdict(track) for track in tracks],
            telegram_id=user.telegram_id,
            chat_id=callback.message.chat.id,
        )
    except Exception:  # noqa: BLE001 — брокер недоступен: снимаем замок и говорим честно
        release_album_lock(user.telegram_id)
        logger.warning("Альбом: очередь недоступна", exc_info=True)
        await callback.answer(t("quick.busy"), show_alert=True)
        return
    await callback.answer()
    await callback.message.answer(
        t("album.queued", title=album.title, count=len(tracks), minutes=estimate_minutes(len(tracks)))
    )

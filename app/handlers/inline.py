"""Инлайн-режим: @бот <запрос> в любом чате — мгновенная выдача треков и минусов.

Работает без проверки подписки (вирусный канал привлечения: каждый отправленный
трек — реклама бота). Отдаются только позиции с tg_file_id — мгновенная пересылка
без скачивания. Включается у BotFather: /setinline.

Под каждым отправленным треком — кнопка входа в бота по РЕФЕРАЛЬНОЙ ссылке
отправителя: тап по «via @bot» бота не открывает (Telegram лишь начинает новый
инлайн-запрос), а кнопку видит весь чат, и приглашённые засчитываются отправителю.
"""
from aiogram import Router
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQuery,
    InlineQueryResultCachedAudio,
    InlineQueryResultsButton,
)
from sqlalchemy import select

from app.config import settings
from app.db.base import session_factory
from app.db.models import Track
from app.services.gamification import referral_link
from app.services.search import search_instrumentals, search_tracks

router = Router()

TRACKS_LIMIT = 10
INSTRUMENTALS_LIMIT = 5
CACHE_SECONDS = 300


def _open_bot_keyboard(sender_telegram_id: int) -> InlineKeyboardMarkup | None:
    """Кнопка «Слушать в TG Music» под треком — по реф-ссылке отправителя."""
    if not settings.bot_username:
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🎧 Слушать в TG Music",
                    url=referral_link(sender_telegram_id, settings.bot_username),
                )
            ]
        ]
    )


async def _latest_tracks(session, limit: int) -> list[Track]:
    stmt = (
        select(Track)
        .where(Track.tg_file_id.is_not(None))
        .order_by(Track.created_at.desc(), Track.id.desc())
        .limit(limit)
    )
    return list((await session.scalars(stmt)).all())


@router.inline_query()
async def inline_search(query: InlineQuery) -> None:
    text = (query.query or "").strip()
    results: list[InlineQueryResultCachedAudio] = []

    async with session_factory() as session:
        if text:
            tracks, _ = await search_tracks(session, text, 1, page_size=TRACKS_LIMIT)
            instrumentals, _ = await search_instrumentals(
                session, text, 1, page_size=INSTRUMENTALS_LIMIT
            )
        else:
            tracks = await _latest_tracks(session, TRACKS_LIMIT)
            instrumentals = []

    keyboard = _open_bot_keyboard(query.from_user.id)

    for track in tracks:
        if track.tg_file_id:
            results.append(
                InlineQueryResultCachedAudio(
                    id=f"t{track.id}",
                    audio_file_id=track.tg_file_id,
                    reply_markup=keyboard,
                )
            )
    for item in instrumentals:
        if item.tg_file_id:
            results.append(
                InlineQueryResultCachedAudio(
                    id=f"i{item.id}",
                    audio_file_id=item.tg_file_id,
                    caption="🎼 Минус",
                    reply_markup=keyboard,
                )
            )

    await query.answer(
        results,
        cache_time=CACHE_SECONDS,
        # Выдача персональная: в кнопке — реф-ссылка отправителя, чужому её отдавать нельзя
        is_personal=True,
        button=InlineQueryResultsButton(text="🎧 Открыть TG Music", start_parameter="inline"),
    )

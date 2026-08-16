"""Инлайн-режим: @бот <запрос> в любом чате — мгновенная выдача треков и минусов.

Работает без проверки подписки (вирусный канал привлечения: каждый отправленный
трек — реклама бота). Отдаются только позиции с tg_file_id — мгновенная пересылка
без скачивания. Включается у BotFather: /setinline.

⚠️ Идентификаторы проверяются на живость ПЕРЕД выдачей. Здесь мы отдаём Telegram
сам file_id, а отправляет его он — значит об отказе нам никто не сообщит, и
самолечение «поймали ошибку при отправке», как в боте и API, тут невозможно.
После переезда на @muz_damn_bot (05.08) 96% каталога держит чужие id, так что
без проверки инлайн выдавал бы почти сплошь нерабочие позиции. Подробности и
ограничения — в services/file_id_health.

Под каждым отправленным треком — кнопка входа в бота по РЕФЕРАЛЬНОЙ ссылке
отправителя: тап по «via @bot» бота не открывает (Telegram лишь начинает новый
инлайн-запрос), а кнопку видит весь чат, и приглашённые засчитываются отправителю.
"""
from aiogram import Bot, Router
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
from app.services.file_id_health import bury_dead_tracks, split_by_liveness
from app.services.gamification import referral_link
from app.services.search import search_instrumentals, search_tracks
from app.i18n import t

router = Router()

TRACKS_LIMIT = 10
INSTRUMENTALS_LIMIT = 5
CACHE_SECONDS = 300

# Во сколько раз просить у базы больше, чем покажем. 96% каталога после переезда
# на @muz_damn_bot держит чужие file_id (замер 15.08), и без запаса выдача после
# отсева мёртвых оказывалась бы пустой. Запас небольшой: проверка каждого — это
# обращение к Bot API, и она ограничена бюджетом (см. services/file_id_health).
POOL_FACTOR = 3


def _open_bot_keyboard(sender_telegram_id: int) -> InlineKeyboardMarkup | None:
    """Кнопка «Слушать в Infinity Music» под треком — по реф-ссылке отправителя."""
    if not settings.bot_username:
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("inline.listen"),
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
async def inline_search(query: InlineQuery, bot: Bot) -> None:
    text = (query.query or "").strip()
    results: list[InlineQueryResultCachedAudio] = []

    async with session_factory() as session:
        if text:
            tracks, _ = await search_tracks(
                session, text, 1, page_size=TRACKS_LIMIT * POOL_FACTOR
            )
            instrumentals, _ = await search_instrumentals(
                session, text, 1, page_size=INSTRUMENTALS_LIMIT * POOL_FACTOR
            )
        else:
            tracks = await _latest_tracks(session, TRACKS_LIMIT * POOL_FACTOR)
            instrumentals = []

        # Инлайн отдаёт сам идентификатор, а не файл: отправить его пробуем не мы,
        # и об отказе Telegram нам не сообщит. Значит проверить надо ДО выдачи —
        # иначе человек в чужом чате не получает ничего и не понимает, почему.
        # Бот и API такое лечат при обращении, инлайн до сих пор не лечил.
        tracks, dead = await split_by_liveness(bot, tracks)
        await bury_dead_tracks(session, dead)
        instrumentals, _ = await split_by_liveness(
            bot, instrumentals, budget=INSTRUMENTALS_LIMIT
        )

    tracks = tracks[:TRACKS_LIMIT]
    instrumentals = instrumentals[:INSTRUMENTALS_LIMIT]
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
                    caption=t("inline.instrumental"),
                    reply_markup=keyboard,
                )
            )

    await query.answer(
        results,
        cache_time=CACHE_SECONDS,
        # Выдача персональная: в кнопке — реф-ссылка отправителя, чужому её отдавать нельзя
        is_personal=True,
        button=InlineQueryResultsButton(text=t("inline.open"), start_parameter="inline"),
    )

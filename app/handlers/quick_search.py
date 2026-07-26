"""Быстрый поиск в боте (запрос владельца): пользователь пишет боту любой текст —
название и/или исполнителя — и сразу получает трек аудиосообщением.

Нашли в базе → шлём лучший трек мгновенно (по кэшированному file_id). Нет →
скрытый поисковый парсер тихо ищет в сети, трек приходит через минуту.

Регистрируется последним: перехватывает только свободный текст без активного FSM
(мастера загрузки/поиска/админки со своими состояниями срабатывают раньше).
"""
import logging

from aiogram import F, Router
from aiogram.types import Message

from app.db.base import session_factory
from app.handlers.common import ensure_user
from app.handlers.delivery import send_track_audio
from app.services.search import search_tracks

logger = logging.getLogger(__name__)

router = Router()


@router.message(F.text & ~F.text.startswith("/"))
async def quick_search(message: Message) -> None:
    query = message.text.strip()
    if not query:
        return
    async with session_factory() as session:
        user = await ensure_user(session, message.from_user)
        tracks, _ = await search_tracks(session, query, page=1)
        if tracks:
            sent = await send_track_audio(message.bot, message.chat.id, session, user, tracks[0])
            if sent is not None:
                return

    # В базе нет — прячем факт парсера, просто «ищу в сети»
    try:
        from app.tasks.search_fetch import search_fetch

        search_fetch.delay(query=query, telegram_id=message.chat.id, chat_id=message.chat.id)
        await message.answer("🔎 Ищу трек — пришлю через минуту.")
    except Exception:  # noqa: BLE001 — брокер недоступен
        await message.answer("Пока не нашёл. Попробуйте уточнить название и исполнителя.")

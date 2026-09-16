"""Выкачка альбома целиком (16.09): все треки по порядку в чат человека.

Очередь `celery`, а НЕ `youtube_user`: альбом на 24 трека — это минуты работы, а
`youtube_user` разбирает выдачу треков всем. Ровно на этом уже обжигались с
переносом плейлистов (два переноса разом останавливали поиск у всех).

Каждый трек идёт той же цепочкой, что одиночный из поиска (`import_candidate`):
уже залитый уходит мгновенно по file_id, новый скачивается с перебором замен при
DRM. Упавший трек не рвёт альбом — он попадает в итоговый список «не удалось».
"""
import asyncio
import logging

from aiogram import Bot

from app.config import settings
from app.db.base import build_task_engine
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

SEND_PAUSE_SECONDS = 1.0  # в один чат Telegram спокойно принимает ~1 сообщение в секунду
_FAILED_SHOWN = 10  # список «не удалось» длиннее десяти уже не читают


async def _language(session, telegram_id: int) -> str:
    from sqlalchemy import select

    from app.db.models import User
    from app.services.users import user_language

    user = await session.scalar(select(User).where(User.telegram_id == telegram_id))
    return user_language(user) if user else "ru"


async def run_album(album: dict, tracks: list[dict], telegram_id: int, chat_id: int, bot=None, factory=None) -> tuple[int, list[str]]:
    """Возвращает (сколько дошло, названия неудачных). bot/factory — для тестов."""
    from app.i18n import t
    from app.services.albums import release_album_lock
    from app.services.stats import record_event
    from app.services.track_lookup.importer import import_candidate
    from app.services.track_lookup.ranking import Candidate

    engine = None
    own_bot = bot is None
    if factory is None:
        engine, factory = build_task_engine()
    if own_bot:
        bot = Bot(token=settings.bot_token)

    title = album.get("title") or "—"
    total = len(tracks)
    delivered = 0
    failed: list[str] = []
    try:
        async with factory() as session:
            lang = await _language(session, telegram_id)
            user_id = await _user_id(session, telegram_id)
            progress = await bot.send_message(chat_id, t("album.progress", lang, title=title, done=0, count=total))
            for number, row in enumerate(tracks, 1):
                candidate = Candidate(**row)
                name = f"{candidate.artist} — {candidate.title}" if candidate.artist else candidate.title
                try:
                    track, _ = await import_candidate(
                        session, bot, candidate, telegram_id, save_to_library=False
                    )
                    if not track.tg_file_id:
                        raise RuntimeError("у трека нет file_id после импорта")
                    await bot.send_audio(
                        chat_id, track.tg_file_id, caption=f"💿 {number}/{total} · {track.artist} — {track.title}"
                    )
                    if user_id:
                        await record_event(session, user_id, track.id, "download", source="worker")
                    delivered += 1
                except Exception:  # noqa: BLE001 — один трек не рвёт альбом
                    logger.warning("Альбом «%s»: трек %s не дошёл", title, name, exc_info=True)
                    failed.append(name)
                    try:
                        await session.rollback()
                    except Exception:  # noqa: BLE001
                        pass
                try:
                    await progress.edit_text(t("album.progress", lang, title=title, done=number, count=total))
                except Exception:  # noqa: BLE001 — прогресс косметика, не повод падать
                    pass
                await asyncio.sleep(SEND_PAUSE_SECONDS)

            summary = t("album.done", lang, title=title, ok=delivered, count=total)
            if failed:
                shown = ", ".join(failed[:_FAILED_SHOWN]) + (" …" if len(failed) > _FAILED_SHOWN else "")
                summary += "\n" + t("album.failed", lang, names=shown)
            await bot.send_message(chat_id, summary)
    finally:
        release_album_lock(telegram_id)
        if own_bot:
            await bot.session.close()
        if engine is not None:
            await engine.dispose()
    return delivered, failed


async def _user_id(session, telegram_id: int) -> int | None:
    from sqlalchemy import select

    from app.db.models import User

    return await session.scalar(select(User.id).where(User.telegram_id == telegram_id))


@celery_app.task(name="album.fetch_all", bind=True, max_retries=0)
def album_fetch_all(self, album: dict, tracks: list[dict], telegram_id: int, chat_id: int) -> None:  # noqa: ARG001
    try:
        asyncio.run(run_album(album, tracks, telegram_id, chat_id))
    except Exception:  # noqa: BLE001 — замок снят в finally; человеку говорим, что не вышло
        logger.exception("Выкачка альбома упала user=%s", telegram_id)

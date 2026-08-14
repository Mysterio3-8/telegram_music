"""Фоновая задача спрятанного поискового парсера #2 (решение владельца).

Находит трек отовсюду по свободному запросу и присылает пользователю в чат.
Живёт в очереди `youtube_user` (рядом с поштучными импортами по ссылке) — не
делит воркер с массовым SoundCloud-сканом.
"""
import asyncio
import logging

from aiogram import Bot

from app.config import settings
from app.db.base import build_task_engine
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def _engine_and_factory():
    return build_task_engine()


async def _with_session(coro):
    engine, factory = _engine_and_factory()
    try:
        async with factory() as session:
            return await coro(session)
    finally:
        await engine.dispose()


async def _record_listen(session, telegram_id: int, track_id: int) -> None:
    """Пишет событие прослушивания за пользователя, получившего трек.

    Раньше эти задачи статистику не писали вообще, хотя именно они — главный путь
    выдачи треков. Из-за этого у приглашённых друзей не было ни одного события, и
    подсчёт рефералов (он требовал «живого» пользователя) стоял на нуле."""
    from app.services.stats import record_event
    from app.services.users import get_user_by_telegram_id

    user = await get_user_by_telegram_id(session, telegram_id)
    if user is not None:
        await record_event(session, user.id, track_id, "listen")


async def _try_best_quality(
    session, bot, track, telegram_id: int, chat_id, source_url=None, caption=None
) -> bool:
    """Пытается отдать трек в платном качестве. False — зовите обычный mp3.

    Отдельной функцией, потому что зовётся из двух мест: отсюда (трек только что
    скачан) и из задачи `search.fetch_best` (трек в базе уже был).

    Любая ошибка гасится и превращается в False: платное качество — надстройка,
    и падать из-за неё задаче нельзя. Celery начал бы её повторять и прислал бы
    человеку тот же трек ещё раз.
    """
    from app.services.original_audio import deliver_best_quality, wants_best_quality
    from app.services.users import get_user_by_telegram_id

    if chat_id is None:
        return False  # «импортировать молча» — это Mini App, файлы в чат он не шлёт
    try:
        user = await get_user_by_telegram_id(session, telegram_id)
        if user is None or not wants_best_quality(user):
            return False
        return await deliver_best_quality(
            session, bot, track, chat_id, source_url=source_url, caption=caption
        )
    except Exception:  # noqa: BLE001 — откатимся на mp3, человек без трека не останется
        logger.warning("Лучшее качество для track=%s не вышло", track.id, exc_info=True)
        return False


@celery_app.task(name="search.fetch_best", bind=True, max_retries=1, queue="youtube_user")
def search_fetch_best(
    self, track_id: int, telegram_id: int, chat_id: int, source_url: str | None = None
) -> None:
    """Платное качество для трека, который в базе уже есть.

    Бот в этом случае НЕ шлёт mp3 заранее: подписчик должен получить один файл,
    а не тот же трек дважды. Значит откат на mp3 — здесь же, иначе при неудаче
    человек остался бы вообще без трека.

    Живёт в воркере по той же причине, что и остальные закачки: десятки
    мегабайт в памяти процесса бота на боксе 961 МБ — это OOM, ронявший прод.
    """
    from app.db.models import Track

    async def _run(session):
        track = await session.get(Track, track_id)
        if track is None:
            return
        bot = Bot(token=settings.bot_token)
        try:
            caption = f"✅ {track.artist} — {track.title}"
            sent = await _try_best_quality(
                session, bot, track, telegram_id, chat_id,
                source_url=source_url, caption=caption,
            )
            if not sent:
                await _send_plain(session, bot, track, telegram_id, chat_id, caption)
            await _record_listen(session, telegram_id, track.id)
        finally:
            await bot.session.close()

    try:
        asyncio.run(_with_session(_run))
    except Exception as exc:  # noqa: BLE001 — одна попытка повтора, дальше сдаёмся
        if self.request.retries >= self.max_retries:
            logger.warning("Лучшее качество track=%s не удалось: %s", track_id, exc)
            return
        raise self.retry(exc=exc, countdown=30)


async def _send_plain(session, bot, track, telegram_id: int, chat_id: int, caption: str) -> None:
    """Обычная выдача трека — то, что получают все. Через `send_track_audio`, а
    не голым `send_audio`: там живёт лечение мёртвых file_id и актуальные теги."""
    from app.handlers.delivery import send_track_audio
    from app.keyboards.track_card import track_card_keyboard
    from app.services.users import get_user_by_telegram_id

    user = await get_user_by_telegram_id(session, telegram_id)
    if user is None:
        return
    await send_track_audio(
        bot, chat_id, session, user, track,
        caption=caption,
        reply_markup=track_card_keyboard(
            track, "srch", in_library=False, bot_username=settings.bot_username
        ),
    )


@celery_app.task(name="search.fetch_candidate", bind=True, max_retries=2, queue="youtube_user")
def search_fetch_candidate(
    self,
    candidate: dict,
    telegram_id: int,
    chat_id: int | None = None,
    save_to_library: bool = True,
) -> None:
    """Качает КОНКРЕТНОГО кандидата, выбранного человеком в выдаче живого поиска.

    Скачивание живёт в воркере, а не в боте, сознательно: mp3 плюс перекодирование
    ffmpeg — это десятки мегабайт пиковой памяти, а бокс на 961 МБ уже дважды
    ронял прод по OOM. Бот остаётся отзывчивым, тяжёлое уходит в очередь.

    chat_id=None — «импортировать молча»: так зовёт Mini App, где человек уже
    слушает поток и присылать ему тот же трек в чат бота не за чем.
    """
    from app.services.track_lookup.importer import import_candidate
    from app.services.track_lookup.ranking import Candidate
    from app.services.youtube.user_import import UserImportRejected

    async def _run(session):
        bot = Bot(token=settings.bot_token)
        chosen = Candidate(**candidate)
        try:
            try:
                track, _ = await import_candidate(
                    session, bot, chosen, telegram_id,
                    save_to_library=save_to_library,
                )
            except UserImportRejected as exc:
                if chat_id is not None:
                    await bot.send_message(chat_id, f"❌ {exc}")
                return
            await _record_listen(session, telegram_id, track.id)
            if chat_id is None:
                return
            caption = f"✅ {track.artist} — {track.title}"

            # Платное качество пробуем ДО обычной отправки: подписчик должен
            # получить один файл, а не тот же трек дважды. Не вышло — ниже
            # уходит обычный mp3, и человек ничего не теряет.
            if await _try_best_quality(
                session, bot, track, telegram_id, chat_id,
                source_url=chosen.url, caption=caption,
            ):
                return

            if chat_id == settings.effective_archive_chat_id:
                # Минт file_id — это реальная отправка файла в архивный чат. Если он
                # не задан, архивом становится чат первого админа, и владелец получал
                # трек дважды: копию минта и нашу. Настоящее лечение — завести
                # TELEGRAM_ARCHIVE_CHAT_ID отдельным каналом; до тех пор не дублируем.
                await bot.send_message(chat_id, f"{caption} — готов.")
            elif track.tg_file_id:
                # Кнопки карточки: добавить в библиотеку/плейлист, скачать, поделиться.
                # Без них у свежескачанного трека не было никаких действий вообще.
                from app.keyboards.track_card import track_card_keyboard

                await bot.send_audio(
                    chat_id,
                    track.tg_file_id,
                    caption=caption,
                    reply_markup=track_card_keyboard(
                        track, "srch", in_library=save_to_library,
                        bot_username=settings.bot_username,
                    ),
                )
            else:
                await bot.send_message(chat_id, f"{caption} — готов.")
        finally:
            await bot.session.close()

    try:
        asyncio.run(_with_session(_run))
    except Exception as exc:  # noqa: BLE001 — повтор с паузой; после ретраев сдаёмся
        if self.request.retries >= self.max_retries:
            logger.warning("Загрузка кандидата %s не удалась: %s", candidate.get("url"), exc)
            return
        raise self.retry(exc=exc, countdown=30)


@celery_app.task(name="search.repair_track", bind=True, max_retries=1, queue="youtube_user")
def repair_track(self, track_id: int, chat_id: int | None = None) -> None:
    """Перевыдаёт file_id треку, чей файл больше не принадлежит текущему боту.

    Скачивание живёт в воркере по той же причине, что и поисковая закачка:
    ffmpeg в процессе бота дважды ронял прод по OOM.
    """
    from app.db.models import Track
    from app.services.track_repair import repair_track_file_id

    async def _run(session):
        track = await session.get(Track, track_id)
        if track is None or track.tg_file_id:
            return  # уже восстановлен параллельной задачей
        bot = Bot(token=settings.bot_token)
        try:
            if not await repair_track_file_id(session, bot, track):
                if chat_id is not None:
                    await bot.send_message(
                        chat_id, f"❌ Не удалось восстановить «{track.artist} — {track.title}»."
                    )
                return
            if chat_id is not None:
                await bot.send_audio(
                    chat_id,
                    track.tg_file_id,
                    caption=f"✅ {track.artist} — {track.title}",
                )
        finally:
            await bot.session.close()

    try:
        asyncio.run(_with_session(_run))
    except Exception as exc:  # noqa: BLE001 — одна попытка повтора, дальше сдаёмся
        if self.request.retries >= self.max_retries:
            logger.warning("Восстановление track=%s не удалось: %s", track_id, exc)
            return
        raise self.retry(exc=exc, countdown=30)


@celery_app.task(name="search.fetch", bind=True, max_retries=2, queue="youtube_user")
def search_fetch(self, query: str, telegram_id: int, chat_id: int, quiet: bool = False) -> None:
    """Ищет трек по запросу отовсюду, минтит и присылает в чат. quiet — без
    сообщения о неудаче (например, авто-дозагрузка по промаху поиска в Mini App)."""
    from app.services.track_lookup.importer import import_by_query
    from app.services.youtube.user_import import UserImportRejected

    async def _run(session):
        bot = Bot(token=settings.bot_token)
        try:
            try:
                track, _ = await import_by_query(session, bot, query, telegram_id)
            except UserImportRejected:
                if not quiet:
                    await bot.send_message(chat_id, f"❌ Не нашли «{query}». Попробуйте иначе.")
                return
            await _record_listen(session, telegram_id, track.id)
            if quiet:
                return
            if track.tg_file_id:
                await bot.send_audio(
                    chat_id, track.tg_file_id,
                    caption=f"✅ {track.artist} — {track.title}\nНашли и добавили в вашу библиотеку.",
                )
            else:
                await bot.send_message(chat_id, f"✅ {track.artist} — {track.title} — добавлен.")
        finally:
            await bot.session.close()

    try:
        asyncio.run(_with_session(_run))
    except Exception as exc:  # noqa: BLE001 — повтор с паузой; после ретраев сообщаем
        if self.request.retries >= self.max_retries:
            logger.warning("Поисковый парсер «%s» не удался: %s", query, exc)
            return
        raise self.retry(exc=exc, countdown=60)

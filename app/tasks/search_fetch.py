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


async def _maybe_send_original(session, bot, track, candidate, telegram_id: int, chat_id) -> None:
    """Досылает оригинальное качество тем, кто его выбрал и оплатил.

    Отдельной функцией, а не строчкой в задаче, потому что зовётся из двух мест:
    отсюда (трек только что скачан) и из задачи `search.fetch_original` (трек в
    базе уже был, скачивать заново нечего).

    Любая ошибка здесь гасится: mp3 человек УЖЕ получил, и падать задаче из-за
    необязательного бонуса нельзя — Celery начнёт её повторять и пришлёт трек
    второй раз.
    """
    from app.services.original_audio import deliver_original, wants_original
    from app.services.users import get_user_by_telegram_id

    if chat_id is None:
        return  # «импортировать молча» — это Mini App, файлы в чат он не шлёт
    try:
        user = await get_user_by_telegram_id(session, telegram_id)
        if user is None or not wants_original(user):
            return
        await deliver_original(
            session, bot, track, chat_id,
            source_url=candidate.url if candidate is not None else None,
            hq_available=bool(candidate.hq_available) if candidate is not None else True,
        )
    except Exception:  # noqa: BLE001 — трек уже доставлен, бонус не обязан удаться
        logger.warning("Оригинал для track=%s не доехал", track.id, exc_info=True)


@celery_app.task(name="search.fetch_original", bind=True, max_retries=1, queue="youtube_user")
def search_fetch_original(
    self, track_id: int, telegram_id: int, chat_id: int, source_url: str | None = None
) -> None:
    """Оригинал для трека, который в базе уже есть (mp3 ушёл мгновенно по file_id).

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
            await _maybe_send_original(
                session, bot, track, _UrlOnly(source_url), telegram_id, chat_id
            )
        finally:
            await bot.session.close()

    try:
        asyncio.run(_with_session(_run))
    except Exception as exc:  # noqa: BLE001 — mp3 человек получил, оригинал не критичен
        logger.warning("Оригинал track=%s не удался: %s", track_id, exc)


class _UrlOnly:
    """Заглушка кандидата для задачи: из выдачи сюда доезжает только ссылка.

    hq_available=True здесь не «мы уверены, что оригинал есть», а «спросить
    источник разрешено» — решение принимает вызывающая сторона в боте, она и
    видела флаг из выдачи."""

    hq_available = True

    def __init__(self, url: str | None) -> None:
        self.url = url


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

            # Оригинал — вторым сообщением и только после того, как mp3 уже у
            # человека: сорок мегабайт заливаются в Telegram десятки секунд, и
            # держать его всё это время без трека было бы хуже, чем сейчас.
            await _maybe_send_original(session, bot, track, chosen, telegram_id, chat_id)
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

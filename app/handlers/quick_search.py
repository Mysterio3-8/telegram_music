"""Живой поиск в боте: пользователь пишет боту любой текст — название и/или
исполнителя — и получает СПИСОК найденных треков кнопками. Тап по кнопке — трек
приходит аудиосообщением.

Ищем сразу в источниках (SoundCloud, затем YouTube тем, чего в SC нет), а не по
локальной базе: каталог мы больше не копим, и именно поиск по базе прятал
андеграунд за пятью похожими совпадениями.

Регистрируется последним: перехватывает только свободный текст без активного FSM
(мастера загрузки/поиска/админки со своими состояниями срабатывают раньше).
"""
import logging
import time
from dataclasses import asdict

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.db.base import session_factory
from app.handlers.common import ensure_user
from app.handlers.cards import build_card_keyboard
from app.handlers.delivery import send_track_audio
from app.keyboards.quick_search import quick_search_keyboard, total_pages
from app.services.library import is_in_library
from app.services.search import find_track_by_metadata, find_track_by_source_url
from app.services.search_cache import search_with_cache
from app.services.search_log import log_search_query
from app.services.track_lookup.importer import candidate_metadata
from app.services.track_lookup.ranking import Candidate
from app.i18n import t

logger = logging.getLogger(__name__)

router = Router()

_QUERY_KEY = "qs_query"  # запрос и кандидаты живут в FSM: в callback_data они не помещаются
_ITEMS_KEY = "qs_items"

# Сколько секунд считать нажатие «ещё в работе». Скачивание с минтом занимает
# ~8 сек, неудачная попытка с перебором замен — до полуминуты; берём с запасом,
# но не бесконечно: если задача потерялась, человек должен иметь возможность
# повторить, а не упереться в вечное «уже качаю».
_FETCH_LOCK_SECONDS = 60.0
_fetch_started: dict[tuple[int, str], float] = {}


def _fetch_in_progress(user_id: int, url: str) -> bool:
    """Занял слот под пару «человек + трек». True — такое же нажатие уже в работе.

    Счётчик в памяти процесса: бот один, а после рестарта забыть незавершённые
    нажатия правильно. В Redis намеренно не пишем — запись на диск при флуде уже
    роняла прод (26.07)."""
    now = time.monotonic()
    for key, started in list(_fetch_started.items()):
        if now - started > _FETCH_LOCK_SECONDS:
            del _fetch_started[key]

    key = (user_id, url)
    if key in _fetch_started:
        return True
    _fetch_started[key] = now
    return False




def _results_title(query: str) -> str:
    return t("quick.results_title", query=query)


async def _stored_candidates(state: FSMContext) -> tuple[str, list[Candidate]]:
    data = await state.get_data()
    rows = data.get(_ITEMS_KEY) or []
    return data.get(_QUERY_KEY, ""), [Candidate(**row) for row in rows]


@router.message(F.text & ~F.text.startswith("/"))
async def quick_search(message: Message, state: FSMContext) -> None:
    query = message.text.strip()
    if not query:
        return
    async with session_factory() as session:
        user = await ensure_user(session, message.from_user)
        # Запрос в журнал: по нему считаются «популярные запросы» и работает
        # прогрев каталога (app.cli.warmup --popular). Раньше журнал заполнял
        # только Mini App, а главный путь поиска — вот этот — молчал, поэтому
        # список популярного оставался пустым.
        await log_search_query(session, user.id, query)

    status = await message.answer(t("quick.searching"))
    candidates = await search_with_cache(query)
    if not candidates:
        await status.edit_text(t("quick.nothing"))
        return

    await state.update_data(
        **{_QUERY_KEY: query, _ITEMS_KEY: [asdict(item) for item in candidates]}
    )
    await status.edit_text(
        _results_title(query), reply_markup=quick_search_keyboard(candidates, page=1)
    )


@router.callback_query(F.data.startswith("qs:p:"))
async def quick_search_page(callback: CallbackQuery, state: FSMContext) -> None:
    page = int(callback.data.split(":")[2])
    query, candidates = await _stored_candidates(state)
    if not candidates:
        await callback.answer(t("quick.stale"), show_alert=True)
        return
    page = max(1, min(page, total_pages(candidates)))
    await callback.message.edit_text(
        _results_title(query), reply_markup=quick_search_keyboard(candidates, page)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("qs:c:"))
async def quick_search_send(callback: CallbackQuery, state: FSMContext) -> None:
    index = int(callback.data.split(":")[2])
    _, candidates = await _stored_candidates(state)
    if index >= len(candidates):
        await callback.answer(t("quick.stale"), show_alert=True)
        return
    candidate = candidates[index]

    # Один и тот же трек, нажатый десять раз подряд, это десять скачиваний в
    # воркере и десять одинаковых ответов человеку (11.08 владелец получил девять
    # подряд «трек под защитой»). Пока предыдущее нажатие в работе — молчим.
    if _fetch_in_progress(callback.from_user.id, candidate.url):
        await callback.answer(t("quick.already_fetching"))
        return

    artist, title = candidate_metadata(candidate)
    async with session_factory() as session:
        user = await ensure_user(session, callback.from_user)
        # Сперва по ссылке источника — точный ключ «этот кандидат уже залит».
        # Сверка по «исполнитель — название» остаётся фолбэком для треков,
        # заведённых до появления source_url.
        existing = await find_track_by_source_url(session, candidate.url)
        if existing is None:
            existing = await find_track_by_metadata(session, artist, title)
        if existing is not None:
            # Уже минтили — отдаём мгновенно по file_id, скачивать нечего.
            # С кнопками карточки: раз в библиотеку сам трек больше не падает,
            # добавить его должно быть чем.
            await callback.answer(t("quick.sending"))
            in_library = await is_in_library(session, user.id, existing.id)
            keyboard = await build_card_keyboard(
                callback.message, existing, "srch", in_library, user.telegram_id
            )
            await send_track_audio(
                callback.bot, callback.message.chat.id, session, user, existing,
                reply_markup=keyboard,
            )
            return

    # Скачивание уходит в воркер: ffmpeg на боксе 961 МБ дважды ронял прод по OOM
    try:
        from app.tasks.search_fetch import search_fetch_candidate

        # Человек попросил прислать трек, а не сохранить его себе: библиотеку
        # трогаем только кнопкой «➕ Добавить в библиотеку» в карточке.
        search_fetch_candidate.delay(
            candidate=asdict(candidate),
            telegram_id=callback.from_user.id,
            chat_id=callback.message.chat.id,
            save_to_library=False,
        )
    except Exception:  # noqa: BLE001 — брокер недоступен, честно об этом говорим
        logger.warning("Живой поиск: очередь недоступна", exc_info=True)
        await callback.answer(t("quick.busy"), show_alert=True)
        return
    await callback.answer(t("quick.downloading"))


@router.callback_query(F.data == "qs:noop")
async def quick_search_noop(callback: CallbackQuery) -> None:
    await callback.answer()

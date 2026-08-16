"""Живость `tg_file_id`: отсев мёртвых идентификаторов до того, как их увидит человек.

🔴 Зачем. `file_id` принадлежит боту, который загрузил файл. После переезда на
@muz_damn_bot (05.08) идентификаторы всего старого каталога стали чужими — замер
15.08: **7223 трека из 7491, 96%**. Бот лечит такой трек при отправке
(`handlers/delivery`), API — при запросе потока (`api/routers/audio`), а вот
инлайн-выдача не лечила ничего: она отдаёт `InlineQueryResultCachedAudio`, то
есть сам идентификатор, и узнать об отказе неоткуда — Telegram не сообщает нам,
что отправка чужого id не удалась. Человек в чужом чате просто не получал трек.

Проверяем `get_file`: он спрашивает Telegram о файле, но НЕ качает его —
килобайты вместо мегабайтов. Тот же приём, что в `cli/repair_catalog`.

⚠️ **Бюджет обязателен.** Инлайн-запрос прилетает на КАЖДОЕ нажатие клавиши, и
проверка всей выдачи на каждое нажатие — это десятки обращений к Bot API в
секунду, то есть свой собственный флуд и 429 от Telegram. Отсюда два ограничения:
кэш вердиктов в памяти процесса (наборы результатов при наборе текста сильно
пересекаются) и потолок обращений на один запрос.

⚠️ **Восстановление ставим не больше одного на запрос.** Пул из тридцати треков
в нынешнем состоянии каталога — это почти тридцать мёртвых, и ставить их все в
очередь значило бы класть на единственное ядро четыре минуты работы за одно
нажатие клавиши. Так уже было: очередь на 177 тысяч задач и OOM (инцидент 03.08).
Гашение же мёртвого id в базе дёшево и делается для всех — оно и подводит трек
под ночной `repair_catalog`, который разбирает их порциями.
"""
import asyncio
import logging
import time

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Track

logger = logging.getLogger(__name__)

# Сколько помнить вердикт. Час: «живой» за это время мёртвым не станет (это
# происходит только при смене токена бота), а «мёртвый» и подавно.
_TTL_SECONDS = 3600.0

# Потолок обращений к Bot API на один инлайн-запрос. Пятнадцать — это вся выдача
# (10 треков + 5 минусов) в худшем случае, когда кэш пуст.
DEFAULT_BUDGET = 15

_verdicts: dict[str, tuple[bool, float]] = {}


def _cached(file_id: str) -> bool | None:
    row = _verdicts.get(file_id)
    if row is None:
        return None
    alive, stamp = row
    if time.monotonic() - stamp > _TTL_SECONDS:
        del _verdicts[file_id]
        return None
    return alive


def _remember(file_id: str, alive: bool) -> None:
    # Словарь растёт только на уникальных file_id и хранит булево на строку;
    # чистим по возрасту при обращении, отдельный сторож тут избыточен.
    if len(_verdicts) > 5000:
        _verdicts.clear()
    _verdicts[file_id] = (alive, time.monotonic())


async def is_alive(bot: Bot, file_id: str) -> bool:
    """Жив ли идентификатор. Сеть моргнула — считаем живым, проверим позже."""
    known = _cached(file_id)
    if known is not None:
        return known
    try:
        await bot.get_file(file_id)
        alive = True
    except TelegramBadRequest:
        alive = False
    except Exception:  # noqa: BLE001 — не наказываем трек за сетевой сбой
        return True
    _remember(file_id, alive)
    return alive


async def split_by_liveness(bot: Bot, items: list, budget: int = DEFAULT_BUDGET) -> tuple[list, list]:
    """Делит записи с `tg_file_id` на живые и мёртвые.

    Непроверенные из-за бюджета в выдачу НЕ попадают: показать мёртвый трек
    хуже, чем показать на один трек меньше — в чужом чате человек не получит
    вообще ничего и не поймёт, почему.
    """
    checked = [item for item in items if item.tg_file_id][:budget]
    if not checked:
        return [], []
    verdicts = await asyncio.gather(
        *(is_alive(bot, item.tg_file_id) for item in checked), return_exceptions=True
    )
    alive, dead = [], []
    for item, verdict in zip(checked, verdicts):
        # Исключение из gather — это сбой проверки, а не приговор треку
        (alive if verdict is True or isinstance(verdict, BaseException) else dead).append(item)
    return alive, dead


async def bury_dead_tracks(
    session: AsyncSession, dead: list[Track], schedule_limit: int = 1
) -> None:
    """Гасит мёртвые id и ставит восстановление — не больше `schedule_limit` штук.

    Гашение делается для всех: оно дёшево и подводит трек под ночной ремонт
    (`cli/repair_catalog` берёт в первую очередь тех, у кого id уже погашен).
    А вот скачивание стоит около восьми секунд ядра, поэтому в очередь уходит
    только первый — тот, который человек, скорее всего, и хотел.

    ⚠️ Только треки. У минусов источника для перезакачки нет (они пришли из
    ТГ-канала), и погасить им id значило бы потерять единственную ссылку на файл
    без всякой возможности восстановить.
    """
    if not dead:
        return
    for track in dead:
        track.tg_file_id = None
        track.meta_synced = False
    await session.commit()
    logger.warning("Инлайн: погашено мёртвых file_id — %d", len(dead))

    for track in dead[:schedule_limit]:
        try:
            from app.tasks.search_fetch import repair_track

            # chat_id=None — «восстановить молча»: инлайн-запрос это не просьба
            # прислать файл, и слать его в чат было бы неожиданностью.
            repair_track.delay(track_id=track.id, chat_id=None)
        except Exception:  # noqa: BLE001 — брокер лёг, починит ночной прогон
            logger.warning("Очередь недоступна, ремонт track=%s отложен", track.id)

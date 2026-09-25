"""Infinity Mix — бесконечная случайная лента без повторов.

Требование владельца (22.09): «включается микс только из минусов, а надо чтобы
рандомные треки, абсолютно рандомные, даже которых нет в базе, без повторов».

Отсюда три правила, и каждое закрывает свою жалобу:

1. **Минусов здесь нет вообще.** Прежний микс собирался через `/mix`, а тот
   уважает сохранённый фильтр «язык = инструментальная». Человек один раз выбрал
   его в «Настроить», значение легло в localStorage — и микс НАВСЕГДА стал
   лентой минусов. Настройка не при чём: для ленты «просто включи музыку» её
   быть не должно.

2. **Половина ленты — из источника, а не из каталога.** 7900 треков кончаются,
   и дальше начинаются повторы. Живые кандидаты играют потоком сразу
   (`/stream/{ref}`), параллельно уходят в очередь на минт.

3. **Без повторов** — и внутри одной ленты, и между днями: показанное пишется в
   `mix_history` и не возвращается семь суток.

⚠️ Каталожная часть идёт первой намеренно: она играет мгновенно по file_id,
пока живая часть ещё резолвит поток. Старт ленты — это первое, что видит
человек, и он не должен ждать сеть.
"""
import asyncio
import logging
import random

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Track
from app.services.recommendations import _recently_shown, _record_shown
from app.services.shelves import SHELVES, interleave, top_artists
from app.services.title_quality import is_probably_junk
from app.services.track_lookup.merge import dedup_key
from app.services.track_lookup.ranking import Candidate

logger = logging.getLogger(__name__)

MIX_SIZE = 24
LIVE_SHARE = 0.45  # какая доля ленты берётся из источника, а не из каталога
SEEDS_PER_CALL = 2  # сколько сидов опрашиваем за один сбор — больше = дольше ответ
# Сколько ждём источник. Лента должна заиграть от каталога почти мгновенно;
# живая часть либо успевает, либо приезжает со следующей порцией.
LIVE_TIMEOUT_SECONDS = 6.0


# Длиннее — это не трек, а альбом одним файлом, концерт или подкаст (в каталоге
# нашлись записи на 50 минут, прогон 25.09). Четверть часа с запасом покрывает
# длинные треки.
MIX_MAX_SECONDS = 15 * 60


async def _catalog_part(session: AsyncSession, user_id: int, limit: int) -> list[Track]:
    """Случайные живые треки каталога, которых человек не слышал за неделю.

    ⚠️ `ORDER BY RANDOM()` по всей таблице — это скан, но берём мы только треки
    с живым file_id, а таких в каталоге тысячи, не миллионы. Когда каталог
    вырастет, здесь понадобится выборка по случайному id-окну.
    """
    shown = await _recently_shown(session, user_id)
    stmt = (
        select(Track)
        .where(
            Track.moderation_status == "approved",
            # Есть чем играть: file_id (мгновенно) или архивная копия.
            # Трек без того и другого — это ожидание вместо музыки.
            or_(Track.tg_file_id.is_not(None), Track.storage_path.is_not(None)),
        )
        .order_by(func.random())
        .limit(limit * 3)  # запас на отсев мусорных названий и истории
    )
    rows = list((await session.scalars(stmt)).all())
    picked: list[Track] = []
    for track in rows:
        if track.id in shown:
            continue
        if is_probably_junk(track.title or ""):
            continue
        if (track.duration or 0) > MIX_MAX_SECONDS:
            continue  # альбом одним файлом или концерт на час — не трек для ленты
        picked.append(track)
        if len(picked) >= limit:
            break
    if not picked and rows:
        # Всё показано за неделю — лучше повтор, чем пустая лента
        picked = rows[:limit]
    return picked


async def _live_part(session: AsyncSession, user_id: int, limit: int) -> list[Candidate]:
    """Кандидаты из источника: любимые артисты человека плюс случайные полки.

    ⚠️ Сиды опрашиваются ПАРАЛЛЕЛЬНО и под общим таймаутом. Последовательно это
    было до четырёх походов в сеть подряд — замер на дев-стенде: запрос ленты не
    укладывался в 20 секунд и клиент его обрывал, то есть музыка не начиналась
    вовсе. Лента обязана заиграть от каталога, а живая часть — это украшение:
    не успела — догрузится следующей порцией.
    """
    from app.services.search_cache import search_with_cache

    seeds: list[str] = []
    artists = await top_artists(session, user_id, limit=2)
    seeds.extend(artists)
    pool = [seed for shelf in SHELVES for seed in shelf.seeds]
    random.shuffle(pool)
    seeds.extend(pool[: max(1, SEEDS_PER_CALL)])

    async def safe(seed: str) -> list[Candidate]:
        try:
            return await search_with_cache(seed)
        except Exception:  # noqa: BLE001 — источник лёг: лента обойдётся каталогом
            logger.warning("Infinity Mix: сид «%s» не ответил", seed, exc_info=True)
            return []

    try:
        groups = await asyncio.wait_for(
            asyncio.gather(*(safe(seed) for seed in seeds)), timeout=LIVE_TIMEOUT_SECONDS
        )
    except asyncio.TimeoutError:
        logger.info("Infinity Mix: источник не успел за %s сек — отдаём каталог", LIVE_TIMEOUT_SECONDS)
        return []
    # Превью Go+ (30 сек) в ленте — это обрыв музыки на полуслове
    mixed = [c for c in interleave(list(groups)) if not c.snippet]
    random.shuffle(mixed)
    return mixed[:limit]


async def build_infinity_mix(
    session: AsyncSession, user_id: int, size: int = MIX_SIZE, with_live: bool = True
) -> tuple[list[Track], list[Candidate]]:
    """Возвращает (треки каталога, живые кандидаты) — уже без пересечений.

    `with_live=False` — первая порция ленты: только база, ноль сетевых походов.
    """
    live_target = int(size * LIVE_SHARE) if with_live else 0
    catalog = await _catalog_part(session, user_id, size - live_target)
    live = await _live_part(session, user_id, live_target) if live_target else []

    seen = {dedup_key(_as_candidate(track)) for track in catalog}
    live = [c for c in live if dedup_key(c) not in seen]

    if catalog:
        await _record_shown(session, user_id, [t.id for t in catalog])
    return catalog, live


def _as_candidate(track: Track) -> Candidate:
    """Трек каталога в форме кандидата — только чтобы посчитать ключ дедупа."""
    return Candidate(
        source="db",
        url=track.source_url or f"db://{track.id}",
        title=track.title or "",
        artist=track.artist or "",
        duration=track.duration or 0,
    )

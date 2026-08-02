"""Полки «настроений» и личный микс без каталога.

Каталог мы больше не копим, а рекомендации всё равно нужны. Живой поиск умеет
отвечать только на конкретный запрос — значит полка и есть набор запросов:
«Драйв» — это несколько сидов, которые уходят в SoundCloud и склеиваются в один
перемешанный список. Личный микс — те же полки плюс артисты, которых человек
реально слушал (история прослушиваний крошечная и живёт в track_events).

Сиды — контент, а не секрет: правятся здесь, деплоем, без миграций.
"""
import random
from dataclasses import dataclass

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Track, TrackEvent
from app.services.track_lookup.merge import dedup_key
from app.services.track_lookup.ranking import Candidate

# Сколько артистов из истории подмешивать в личный микс. Больше — микс сползает
# в повтор уже прослушанного; меньше — перестаёт быть личным.
PERSONAL_ARTISTS = 5


@dataclass(frozen=True)
class Shelf:
    slug: str
    name: str
    seeds: tuple[str, ...]


SHELVES: tuple[Shelf, ...] = (
    Shelf("drive", "Драйв", ("russian phonk", "hard trap 2026", "drift phonk", "агрессивный рэп")),
    Shelf("chill", "Вечер", ("lofi hip hop", "chill rnb", "спокойный рэп", "ambient beats")),
    Shelf("rus", "Русский рэп", ("русский рэп 2026", "новый рэп", "underground rap russia")),
    Shelf("hits", "Свежее", ("new music 2026", "fresh drops", "новинки музыки")),
    Shelf("underground", "Андеграунд", ("underground rap", "андеграунд рэп", "raw demo tape")),
)


def get_shelf(slug: str) -> Shelf | None:
    return next((shelf for shelf in SHELVES if shelf.slug == slug), None)


def interleave(groups: list[list[Candidate]]) -> list[Candidate]:
    """По одному треку из каждой группы по кругу — чтобы полка не начиналась
    десятью треками одного сида. Дубликаты между группами схлопываются."""
    result: list[Candidate] = []
    seen: set[str] = set()
    for row in range(max((len(group) for group in groups), default=0)):
        for group in groups:
            if row >= len(group):
                continue
            candidate = group[row]
            key = dedup_key(candidate)
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            result.append(candidate)
    return result


async def top_artists(session: AsyncSession, user_id: int, limit: int = PERSONAL_ARTISTS) -> list[str]:
    """Артисты, которых пользователь слушал чаще всего. Пусто — новичок."""
    stmt = (
        select(Track.artist, func.count().label("plays"))
        .join(TrackEvent, TrackEvent.track_id == Track.id)
        .where(TrackEvent.user_id == user_id, TrackEvent.event == "listen")
        .group_by(Track.artist)
        .order_by(desc("plays"))
        .limit(limit)
    )
    return [row[0] for row in (await session.execute(stmt)).all() if row[0]]


async def build_shelf(shelf: Shelf) -> list[Candidate]:
    """Треки полки: каждый сид уходит в живой поиск, результаты чередуются."""
    from app.services.search_cache import search_with_cache

    groups = [await search_with_cache(seed) for seed in shelf.seeds]
    return interleave(groups)


async def build_personal_mix(session: AsyncSession, user_id: int) -> list[Candidate]:
    """Личный микс: любимые артисты впереди, следом свежее из общих полок.

    Новичку истории неоткуда взяться — он получает те же полки, и это честнее,
    чем показывать пустой экран.
    """
    from app.services.search_cache import search_with_cache

    artists = await top_artists(session, user_id)
    groups = [await search_with_cache(name) for name in artists]
    groups.extend([await search_with_cache(seed) for seed in get_shelf("hits").seeds])
    mixed = interleave(groups)
    random.shuffle(mixed)
    return mixed

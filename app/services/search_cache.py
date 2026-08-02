"""Кэш выдачи живого поиска.

Пять человек за час пишут «розовое вино» — в сеть надо сходить один раз. Кэш
именно ускоряет, а не требуется: Redis лёг — поиск работает, просто медленнее.
Ключ — нормализованный запрос, поэтому «Кизару Фейк Айди» и «kizaru fake id»
попадают в одну запись.
"""
import json
import logging
from dataclasses import asdict

from app.config import settings
from app.services.track_lookup.ranking import Candidate, normalize_query

logger = logging.getLogger(__name__)

_PREFIX = "livesearch:"


def _client():
    """Redis-клиент или None, если Redis не настроен/недоступен."""
    if not settings.redis_url:
        return None
    try:
        import redis.asyncio as redis

        return redis.from_url(settings.redis_url, decode_responses=True)
    except Exception:  # noqa: BLE001 — библиотека/URL/сеть: кэш опционален
        logger.warning("Кэш поиска: Redis недоступен", exc_info=True)
        return None


def cache_key(query: str) -> str:
    return _PREFIX + normalize_query(query)


def encode(candidates: list[Candidate]) -> str:
    return json.dumps([asdict(item) for item in candidates], ensure_ascii=False)


def decode(raw: str) -> list[Candidate]:
    return [Candidate(**row) for row in json.loads(raw)]


async def get_cached(query: str) -> list[Candidate] | None:
    client = _client()
    if client is None:
        return None
    try:
        raw = await client.get(cache_key(query))
        return decode(raw) if raw else None
    except Exception:  # noqa: BLE001 — кэш не обязан работать
        logger.warning("Кэш поиска: чтение не удалось", exc_info=True)
        return None
    finally:
        await client.aclose()


async def put_cached(query: str, candidates: list[Candidate]) -> None:
    if not candidates:
        return  # пустую выдачу не кэшируем: трек мог появиться в источнике минуту назад
    client = _client()
    if client is None:
        return
    try:
        await client.set(
            cache_key(query), encode(candidates), ex=settings.search_cache_ttl_seconds
        )
    except Exception:  # noqa: BLE001
        logger.warning("Кэш поиска: запись не удалась", exc_info=True)
    finally:
        await client.aclose()


async def search_with_cache(query: str, limit: int | None = None) -> list[Candidate]:
    """Живой поиск через кэш: попадание отдаёт мгновенно, промах идёт в источники."""
    from app.services.track_lookup import search_candidates

    cached = await get_cached(query)
    if cached is not None:
        return cached
    candidates = await search_candidates(query, limit)
    await put_cached(query, candidates)
    return candidates

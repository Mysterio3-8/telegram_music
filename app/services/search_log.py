"""Реальные поисковые запросы Mini App: лог + топ популярных (ТЗ §11).

Логируются только «закоммиченные» запросы (Enter / тап по подсказке),
а не каждый символ дебаунса — иначе топ забьют обрезки вроде «ки», «кин».
"""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SearchQuery

MIN_QUERY_LENGTH = 2
MAX_QUERY_LENGTH = 100
POPULAR_LIMIT = 10


async def log_search_query(session: AsyncSession, user_id: int, query: str) -> bool:
    """Сохраняет запрос. Возвращает False для мусора (слишком короткий/длинный)."""
    text = " ".join(query.split())
    if not (MIN_QUERY_LENGTH <= len(text) <= MAX_QUERY_LENGTH):
        return False
    session.add(SearchQuery(user_id=user_id, query=text))
    await session.commit()
    return True


async def popular_queries(session: AsyncSession, limit: int = POPULAR_LIMIT) -> list[str]:
    """Топ запросов по частоте, регистронезависимая группировка."""
    key = func.lower(SearchQuery.query)
    rows = await session.execute(
        select(func.min(SearchQuery.query))
        .group_by(key)
        .order_by(func.count().desc(), func.min(SearchQuery.query))
        .limit(limit)
    )
    return [row[0] for row in rows.all()]

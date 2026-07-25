"""Поиск трека по свободному запросу пользователя сразу во всех источниках.

Массовое пополнение каталога 24/7 работает только с SoundCloud; этот модуль —
вторая, независимая ветка: пользователь пишет запрос как угодно, а мы ищем везде
и выбираем лучшее совпадение. Вызовы блокирующие (yt-dlp) — оборачивать
в asyncio.to_thread на стороне вызывающего.
"""
from app.services.track_lookup.providers import (
    PROVIDERS,
    SOURCE_SOUNDCLOUD,
    SOURCE_YOUTUBE,
    collect_candidates,
    search_soundcloud,
    search_youtube,
)
from app.services.track_lookup.ranking import (
    Candidate,
    best_match,
    match_score,
    normalize_query,
    rank_candidates,
    to_latin,
)


def find_track(query: str, limit: int = 5) -> Candidate | None:
    """Лучшее совпадение по запросу среди всех источников; None — не нашли."""
    return best_match(query, collect_candidates(query, limit))


__all__ = [
    "Candidate",
    "PROVIDERS",
    "SOURCE_SOUNDCLOUD",
    "SOURCE_YOUTUBE",
    "best_match",
    "collect_candidates",
    "find_track",
    "match_score",
    "normalize_query",
    "rank_candidates",
    "search_soundcloud",
    "search_youtube",
    "to_latin",
]

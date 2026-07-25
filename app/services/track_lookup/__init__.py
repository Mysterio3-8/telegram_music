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

# Порог уверенного совпадения понижен: владелец хочет выдачу даже по слабому
# запросу. best_match вызываем с ним; ниже порога — фолбэк на топ (см. find_track).
CONFIDENT_MATCH = 0.3


def find_track(query: str, limit: int = 8) -> Candidate | None:
    """Лучшее совпадение по запросу среди всех источников; None — не нашли.

    Владелец: выдавать трек даже по слабому запросу (одно слово, только артист,
    только альбом, одна буква). Поэтому если ни один кандидат не дотянул до
    порога уверенного совпадения — отдаём топ по ранжированию (что-то релевантное
    лучше, чем «не нашли»). None только когда источники не вернули ничего."""
    candidates = collect_candidates(query, limit)
    confident = best_match(query, candidates, min_score=CONFIDENT_MATCH)
    if confident is not None:
        return confident
    ranked = rank_candidates(query, candidates)
    if ranked:
        return ranked[0]
    # ранжирование отбросило всё (мусор/ноль) — берём первый непустой кандидат
    return candidates[0] if candidates else None


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

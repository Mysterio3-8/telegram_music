"""Склейка выдачи двух источников в один список для пользователя.

Решение владельца: SoundCloud приоритетный и берётся целиком; YouTube добавляет
только то, чего в SoundCloud нет. Дубликат узнаём по нормализованной паре
«артист + название» — через транслит, поэтому «Kizaru — Fake ID» с YouTube
опознаётся как тот же трек, что «кизару фейк айди» с SoundCloud.

Здесь только вычисления: ни сети, ни БД.
"""
from app.services.track_lookup.ranking import Candidate, normalize_query


def dedup_key(candidate: Candidate) -> str:
    """Ключ «это один и тот же трек». Пустой ключ — кандидат без опознавательных
    знаков, такие не схлопываем: лучше показать дважды, чем потерять."""
    return normalize_query(candidate.full_title)


def merge_candidates(primary: list[Candidate], extra: list[Candidate]) -> list[Candidate]:
    """primary целиком, следом уникальные из extra. Порядок внутри каждого списка
    сохраняется — ранжирование уже отработало до склейки."""
    merged = list(primary)
    seen = {key for key in (dedup_key(item) for item in primary) if key}
    for candidate in extra:
        key = dedup_key(candidate)
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        merged.append(candidate)
    return merged

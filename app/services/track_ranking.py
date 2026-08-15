"""Порядок треков ИЗ НАШЕЙ БАЗЫ под запрос человека.

Живой поиск по источникам давно ранжируется (`track_lookup.ranking`), а поиск по
собственной базе всё это время сортировался `ORDER BY artist, title` — то есть по
алфавиту. Отсюда жалоба на инлайн: по запросу «kizaru» первым шёл
«044ROSE — STOP XANAX ДЭМО ДЛЯ КИЗАРУ», просто потому что ноль стоит раньше букв.

Считаем тем же аппаратом, что и живой поиск: похожесть, попадание в имя артиста,
попадание в название. Прослушиваний у строки таблицы под рукой нет, и лезть за
ними в `track_events` на каждый поиск дорого — здесь их и нет.
"""
from app.db.models import Track
from app.services.track_lookup.ranking import (
    Candidate,
    artist_affinity,
    match_score,
    title_hit,
)

# Вес попадания в имя артиста выше веса попадания в название — ровно как в живом
# поиске, и по той же причине: когда точной песни нет, правильный артист полезнее
# чужого трека с похожим названием.
_ARTIST_BONUS = 0.35
_TITLE_BONUS = 0.25


def _as_candidate(track: Track) -> Candidate:
    """Строка таблицы в том виде, в каком её понимает ранжирование."""
    return Candidate(
        source="library",
        url=track.source_url or f"track:{track.id}",
        title=track.title or "",
        duration=track.duration or 0,
        artist=track.artist or None,
    )


def track_relevance(query: str, track: Track) -> float:
    candidate = _as_candidate(track)
    return (
        match_score(query, candidate)
        + artist_affinity(query, candidate) * _ARTIST_BONUS
        + title_hit(query, candidate) * _TITLE_BONUS
    )


def rank_tracks(query: str, tracks: list[Track]) -> list[Track]:
    """Треки от лучшего к худшему. Ничего не выбрасывает — только меняет порядок.

    ⚠️ Именно не выбрасывает, в отличие от ранжирования живого поиска. Там мы
    отсеиваем мусор источника, а здесь каждая строка уже прошла отбор при
    импорте: выкинуть её из выдачи значило бы спрятать от человека трек, который
    у нас есть.
    """
    if not query.strip():
        return tracks
    return sorted(tracks, key=lambda item: track_relevance(query, item), reverse=True)

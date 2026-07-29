"""Поиск по любому слову/букве, включая кириллицу (требование владельца)."""
import pytest

from app.db.models import Track
from app.services.search import search_tracks
from app.services.search_index import build_search_index


def _track(artist: str, title: str) -> Track:
    return Track(
        title=title, artist=artist, duration=200,
        search_index=build_search_index(artist, title),
    )


def test_index_lowercases_and_adds_translit():
    index = build_search_index("Кизару", "Фейк Айди")
    assert "кизару фейк айди" in index
    assert "kizaru feyk aydi" in index  # транслит для латинских запросов


def test_index_ascii_only_not_duplicated():
    assert build_search_index("Kizaru", "Fake ID") == "kizaru fake id"


@pytest.mark.asyncio
async def test_search_finds_by_single_cyrillic_letter(session):
    """Главная жалоба: «ки» русскими буквами ничего не находило на SQLite."""
    session.add_all([
        _track("Кизару", "Фейк Айди"),
        _track("Big Baby Tape", "Gimme the Loot"),
    ])
    await session.commit()

    for query in ("к", "ки", "КИЗ", "кизару", "айди", "фейк айди"):
        tracks, total = await search_tracks(session, query, page=1)
        assert total == 1, f"запрос «{query}» ничего не нашёл"
        assert tracks[0].artist == "Кизару"


@pytest.mark.asyncio
async def test_search_by_translit_and_author(session):
    session.add_all([_track("Кизару", "Фейк Айди"), _track("Miyagi", "Kosandra")])
    await session.commit()

    # латиницей ищем кириллический трек
    tracks, total = await search_tracks(session, "kizaru", page=1)
    assert total == 1 and tracks[0].artist == "Кизару"
    # по автору
    tracks, total = await search_tracks(session, "miyagi", page=1)
    assert total == 1 and tracks[0].title == "Kosandra"
    # по любому куску названия
    tracks, total = await search_tracks(session, "sandr", page=1)
    assert total == 1 and tracks[0].title == "Kosandra"


@pytest.mark.asyncio
async def test_tracks_without_index_still_found(session):
    """Бэкфилл идёт фоном — старые треки без индекса не должны пропадать из поиска."""
    session.add(Track(title="Legacy Song", artist="Old Artist", duration=100))
    await session.commit()
    tracks, total = await search_tracks(session, "legacy", page=1)
    assert total == 1 and tracks[0].title == "Legacy Song"

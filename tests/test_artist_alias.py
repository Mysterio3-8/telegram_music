"""Кириллица → латинское имя артиста из базы; YouTube не держит выдачу (прогон 25.09)."""
import asyncio
import time

import pytest

from app.services import track_lookup
from app.services.track_lookup.artist_alias import build_index, latin_variant
from app.services.track_lookup.ranking import Candidate

INDEX = build_index(
    ["Big Baby Tape", "Pop Smoke", "Kizaru", "Macan", "Скриптонит", "Egor Rakitin", "OG Buda", "Veche"]
)


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("биг бейби тейп драгонборн", "Big Baby Tape dragonborn"),
        ("биг бейби тейп драгонбон", "Big Baby Tape dragonbon"),
        ("поп смоук диор", "Pop Smoke dior"),
        ("кизару", "Kizaru"),
        ("макан", "Macan"),
    ],
)
def test_cyrillic_artist_gets_latin_name(query, expected):
    assert latin_variant(query, INDEX) == expected


@pytest.mark.parametrize(
    "query",
    [
        "big baby tape dragonborn",  # уже латиница — подсказка не нужна
        "вечно молодой",  # одно короткое похожее слово — не подставляем
        "мак",  # короче пяти букв в одиночку
        "",
    ],
)
def test_no_variant(query):
    assert latin_variant(query, INDEX) is None


def test_empty_index_is_quiet():
    assert latin_variant("биг бейби тейп", {}) is None


def _c(title, artist):
    return Candidate(source="soundcloud", url=f"https://sc/{title}", title=title, duration=200, artist=artist)


def test_latin_search_does_not_wait_for_hung_youtube(monkeypatch):
    monkeypatch.setattr(track_lookup, "YOUTUBE_GRACE", 0.3)

    def slow_youtube(query, limit):
        time.sleep(3)
        return []

    monkeypatch.setattr(track_lookup, "search_youtube", slow_youtube)
    monkeypatch.setattr(
        track_lookup, "search_soundcloud", lambda q, limit: [_c("Dragonborn", "Big Baby Tape")]
    )
    async def timed():
        started = time.monotonic()
        found = await track_lookup.search_candidates("big baby tape dragonborn")
        return found, time.monotonic() - started

    # asyncio.run при закрытии дождётся потока — меряем внутри цикла, как в боте
    result, elapsed = asyncio.run(timed())
    assert elapsed < 2
    assert result and result[0].title == "Dragonborn"


def test_cyrillic_query_searches_latin_artist_name(monkeypatch):
    asked = []

    def soundcloud(query, limit):
        asked.append(query)
        return [_c("Dragonborn", "Big Baby Tape")] if query.startswith("Big Baby Tape") else []

    monkeypatch.setattr(track_lookup, "search_soundcloud", soundcloud)
    monkeypatch.setattr(track_lookup, "search_youtube", lambda q, limit: [])
    monkeypatch.setattr(
        "app.services.track_lookup.artist_alias._get_index", lambda: INDEX
    )
    result = asyncio.run(track_lookup.search_candidates("биг бейби тейп драгонборн"))
    assert "Big Baby Tape dragonborn" in asked
    assert result and result[0].title == "Dragonborn"

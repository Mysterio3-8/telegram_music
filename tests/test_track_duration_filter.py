"""Фильтр «только треки» поискового парсера (приоритет владельца)."""
import pytest

from app.config import settings
from app.services.track_lookup import find_track, is_track_duration
from app.services.track_lookup.providers import _to_seconds
from app.services.track_lookup.ranking import Candidate, match_score, rank_candidates


@pytest.fixture(autouse=True)
def _fixed_bounds(monkeypatch):
    monkeypatch.setattr(settings, "search_min_seconds", 60)
    monkeypatch.setattr(settings, "search_max_seconds", 720)


def test_duration_bounds():
    assert is_track_duration(180) is True  # обычный трек
    assert is_track_duration(10) is False  # обрезок/джингл
    assert is_track_duration(3600) is False  # часовой микс/подкаст
    assert is_track_duration(60) is True  # ровно нижняя граница
    assert is_track_duration(720) is True  # ровно верхняя граница
    assert is_track_duration(0) is True  # неизвестна — проверим после скачивания


def test_bounds_disabled_when_zero(monkeypatch):
    monkeypatch.setattr(settings, "search_min_seconds", 0)
    monkeypatch.setattr(settings, "search_max_seconds", 0)
    assert is_track_duration(5) is True and is_track_duration(9999) is True


def test_soundcloud_milliseconds_converted():
    assert _to_seconds(213_000) == 213  # SoundCloud отдаёт миллисекунды
    assert _to_seconds(213) == 213  # yt-dlp местами уже секунды
    assert _to_seconds(None) == 0


def test_match_score_zero_for_wrong_duration():
    short = Candidate(source="soundcloud", url="u1", title="Kizaru Fake ID", duration=12)
    long = Candidate(source="soundcloud", url="u2", title="Kizaru Fake ID", duration=4000)
    good = Candidate(source="soundcloud", url="u3", title="Kizaru Fake ID", duration=200)
    assert match_score("kizaru fake id", short) == 0.0
    assert match_score("kizaru fake id", long) == 0.0
    assert match_score("kizaru fake id", good) > 0


def test_rank_drops_non_tracks():
    candidates = [
        Candidate(source="soundcloud", url="u1", title="Kizaru Fake ID", duration=8),
        Candidate(source="soundcloud", url="u2", title="Kizaru Fake ID", duration=200),
    ]
    ranked = rank_candidates("kizaru fake id", candidates)
    assert [c.url for c in ranked] == ["u2"]


def test_original_beats_slowed_version():
    """Просили оригинал — slowed/reverb не должен его обгонять (жалоба владельца)."""
    original = Candidate(source="soundcloud", url="orig",
                         title="Big Baby Tape - Gimme The Loot", duration=200)
    slowed = Candidate(source="soundcloud", url="slow",
                       title="Big Baby Tape - Gimme The Loot (slowed)", duration=240)
    ranked = rank_candidates("big baby tape gimme the loot", [slowed, original])
    assert ranked[0].url == "orig"


def test_slowed_wins_when_asked_explicitly():
    """Если человек просит именно slowed — отдаём её."""
    original = Candidate(source="soundcloud", url="orig",
                         title="Розовое вино", duration=200)
    slowed = Candidate(source="soundcloud", url="slow",
                       title="Розовое вино (Slowed + Reverb)", duration=240)
    ranked = rank_candidates("розовое вино slowed", [original, slowed])
    assert ranked[0].url == "slow"


def test_find_track_never_returns_junk_fallback(monkeypatch):
    """Даже когда ничего не совпало, часовой микс не выдаётся вместо трека."""
    junk = [Candidate(source="soundcloud", url="j", title="Full Album Mix", duration=5400)]
    monkeypatch.setattr("app.services.track_lookup.search_soundcloud", lambda q, l: junk)
    monkeypatch.setattr("app.services.track_lookup.search_youtube", lambda q, l: [])
    assert find_track("что-то непохожее") is None


def test_find_track_falls_back_to_valid_candidate(monkeypatch):
    """Слабое совпадение по названию, но это настоящий трек — отдаём его."""
    ok = [Candidate(source="soundcloud", url="ok", title="Совсем другое имя", duration=200)]
    monkeypatch.setattr("app.services.track_lookup.search_soundcloud", lambda q, l: ok)
    monkeypatch.setattr("app.services.track_lookup.search_youtube", lambda q, l: [])
    found = find_track("zzz")
    assert found is not None and found.url == "ok"

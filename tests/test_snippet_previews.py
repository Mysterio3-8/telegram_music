"""Превью Go+ на 30 сек не выдаются за трек (живой прогон 25.09, Infinity Mix)."""
from app.services import soundcloud_api
from app.services.track_lookup import importer
from app.services.track_lookup.ranking import Candidate


def _item(**over):
    item = {
        "permalink_url": "https://soundcloud.com/playboicarti/new-choppa",
        "title": "New Choppa (feat. A$AP Rocky)",
        "user": {"username": "playboicarti"},
        "duration": 30000,
        "full_duration": 183000,
        "policy": "SNIP",
    }
    item.update(over)
    return item


def test_snip_policy_is_snippet():
    assert soundcloud_api.is_snippet(_item())


def test_short_stream_is_snippet_even_without_policy():
    assert soundcloud_api.is_snippet(_item(policy="MONETIZE"))


def test_normal_track_is_not_snippet():
    assert not soundcloud_api.is_snippet(_item(policy="ALLOW", duration=183000))
    assert not soundcloud_api.is_snippet({"duration": 183000})


def test_candidate_shows_real_length_and_flag():
    candidate = soundcloud_api._to_candidate(_item())
    assert candidate.snippet is True
    assert candidate.duration == 183  # а не 30 — длина трека, не превью


def test_snippet_is_not_downloaded_from_soundcloud(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "app.services.soundcloud_fast.fast_download", lambda url: calls.append(url)
    )
    monkeypatch.setattr(importer, "download_soundcloud_audio", lambda *a, **k: calls.append(a))
    snippet = Candidate(source="soundcloud", url="https://sc/x", title="New Choppa", duration=183, snippet=True)
    assert importer.download_candidate(snippet) is None
    assert calls == []


def test_fallback_skips_snippet_replacements(monkeypatch):
    original = Candidate(
        source="soundcloud", url="https://sc/orig", title="New Choppa", artist="Playboi Carti",
        duration=183, snippet=True,
    )
    snip_copy = Candidate(
        source="soundcloud", url="https://sc/copy", title="New Choppa", artist="Playboi Carti",
        duration=183, snippet=True,
    )
    full = Candidate(
        source="youtube", url="https://youtu.be/abcdefghijk", title="New Choppa",
        artist="Playboi Carti", duration=184,
    )
    tried = []

    def fake_download(candidate):
        tried.append(candidate.url)
        return "AUDIO" if candidate is full else None

    monkeypatch.setattr(importer, "download_candidate", fake_download)
    monkeypatch.setattr(importer, "search_soundcloud", lambda q, limit: [snip_copy])
    monkeypatch.setattr(importer, "search_youtube", lambda q, limit: [full])
    assert importer.download_with_fallback(original) == "AUDIO"
    assert "https://sc/copy" not in tried


def test_dedup_prefers_full_copy_over_preview():
    from app.services.track_lookup.merge import dedup_candidates

    preview = Candidate(source="soundcloud", url="https://sc/official", title="Dior", artist="Pop Smoke",
                        duration=216, official=True, snippet=True)
    full = Candidate(source="soundcloud", url="https://sc/reupload", title="Dior", artist="Pop Smoke",
                     duration=216)
    other = Candidate(source="soundcloud", url="https://sc/o", title="Gangstas", artist="Pop Smoke", duration=190)
    result = dedup_candidates([preview, other, full])
    assert [c.url for c in result] == ["https://sc/reupload", "https://sc/o"]


def test_dead_catalog_copy_yields_live_stream():
    """Прогон 25.09: Dior из поиска вёл в мёртвую запись каталога — 0:00."""
    from types import SimpleNamespace

    from app.api.routers.live_search import _worth_catalog

    live = Candidate(source="soundcloud", url="https://sc/d", title="Dior", duration=216)
    preview = Candidate(source="soundcloud", url="https://sc/p", title="Dior", duration=216, snippet=True)
    dead = SimpleNamespace(tg_file_id=None, storage_path=None)
    alive = SimpleNamespace(tg_file_id="id", storage_path=None)
    assert _worth_catalog(alive, live)
    assert not _worth_catalog(dead, live)  # живой поток играет сразу
    assert _worth_catalog(dead, preview)  # поток дал бы 30 сек — пусть каталог ищет копию


def test_track_number_prefix_is_not_part_of_artist():
    from app.services.title_parser import parse_title

    assert parse_title("1. Big Baby Tape - Dragonborn", "x") == ("Big Baby Tape", "Dragonborn")
    assert parse_title("12) Kizaru - Зеркало", "x") == ("Kizaru", "Зеркало")
    assert parse_title("50 Cent - In Da Club", "x") == ("50 Cent", "In Da Club")
    assert parse_title("2 Chainz - Birthday Song", "x")[0] == "2 Chainz"

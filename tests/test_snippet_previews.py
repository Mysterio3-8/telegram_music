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

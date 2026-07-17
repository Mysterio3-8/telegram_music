from app.services.soundcloud import (
    collect_soundcloud_entries,
    extract_soundcloud_url,
    is_soundcloud_link,
)


def test_is_soundcloud_link():
    assert is_soundcloud_link("https://soundcloud.com/user/track-name")
    assert is_soundcloud_link("вот мой бит soundcloud.com/beatmaker/fire-beat забери")
    assert is_soundcloud_link("https://on.soundcloud.com/AbCdEf")
    assert is_soundcloud_link("https://m.soundcloud.com/user/sets/beats")
    assert not is_soundcloud_link("https://youtube.com/watch?v=abc")
    assert not is_soundcloud_link("просто текст")


def test_extract_soundcloud_url_adds_scheme():
    assert extract_soundcloud_url("soundcloud.com/user/track") == "https://soundcloud.com/user/track"
    assert extract_soundcloud_url("нет ссылки") is None


def test_collect_entries_single_track():
    info = {"url": None, "webpage_url": "https://soundcloud.com/u/track1", "title": "Fire Beat"}
    entries = collect_soundcloud_entries(info)
    assert len(entries) == 1
    assert entries[0].title == "Fire Beat"


def test_collect_entries_profile_dedups():
    info = {
        "entries": [
            {"url": "https://soundcloud.com/u/track1", "title": "Beat 1"},
            {"url": "https://soundcloud.com/u/track2", "title": "Beat 2"},
            {"url": "https://soundcloud.com/u/track1", "title": "Beat 1 dup"},
            {"url": "https://example.com/other", "title": "чужое"},
        ]
    }
    entries = collect_soundcloud_entries(info)
    assert [e.title for e in entries] == ["Beat 1", "Beat 2"]

from unittest.mock import patch

from app.services.search_download import (
    _first_entry,
    build_search_specs,
    clean_query,
    search_and_download,
)


def test_clean_query_collapses_whitespace():
    assert clean_query("  kizaru   фейк   айди ") == "kizaru фейк айди"
    assert clean_query("") == ""
    assert clean_query(None) == ""


def test_build_search_specs_order_soundcloud_first():
    specs = build_search_specs("элджей розовое вино")
    assert specs == ["scsearch1:элджей розовое вино", "ytsearch1:элджей розовое вино"]


def test_build_search_specs_empty():
    assert build_search_specs("   ") == []


def test_first_entry_unwraps_search_result():
    assert _first_entry(None) is None
    assert _first_entry({"title": "solo"}) == {"title": "solo"}
    wrapped = {"entries": [None, {"title": "hit"}]}
    assert _first_entry(wrapped) == {"title": "hit"}


def test_search_and_download_tries_next_source_on_failure():
    """SoundCloud кинул ошибку → пробуем YouTube; первый успех возвращается."""
    calls = []

    def fake_download(spec):
        calls.append(spec)
        if spec.startswith("scsearch"):
            raise RuntimeError("SC 404")
        return ("audio", "uploader")

    with patch("app.services.search_download._download_spec", side_effect=fake_download):
        result = search_and_download("some track")
    assert result == ("audio", "uploader")
    assert calls == ["scsearch1:some track", "ytsearch1:some track"]


def test_search_and_download_none_when_all_empty():
    with patch("app.services.search_download._download_spec", return_value=None):
        assert search_and_download("nothing") is None

import os

from app.config import settings
from app.services.audio_cache import _cache_path, cache_get, cache_put


def test_roundtrip():
    cache_put("tracks/1", b"audio-bytes")

    assert cache_get("tracks/1") == b"audio-bytes"


def test_miss_returns_none():
    assert cache_get("tracks/404") is None


def test_disabled_when_limit_zero(monkeypatch):
    monkeypatch.setattr(settings, "audio_cache_max_mb", 0)

    cache_put("tracks/2", b"data")

    assert cache_get("tracks/2") is None


def test_lru_evicts_oldest(monkeypatch):
    monkeypatch.setattr(settings, "audio_cache_max_mb", 1)
    chunk = b"x" * (600 * 1024)  # два таких не влезают в лимит 1 МБ

    cache_put("tracks/old", chunk)
    os.utime(_cache_path("tracks/old"), (1, 1))  # состарить: LRU-жертва
    cache_put("tracks/new", chunk)

    assert cache_get("tracks/old") is None
    assert cache_get("tracks/new") == chunk

"""Одна ссылка — один импорт, даже когда её тянут два потока сразу (24.09).

Находка сверки прода: «BONES — Dashboard» заведён дважды (33007/33008) с одной
ссылкой и разницей в секунду.
"""
import pytest

from app.db.models import Track
from app.services import import_lock
from app.services.track_lookup import importer
from app.services.track_lookup.ranking import Candidate

URL = "https://soundcloud.com/lilbasedjit6/bones-dashboard"


class FakeRedis:
    def __init__(self):
        self.keys: dict[str, str] = {}

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.keys:
            return None
        self.keys[key] = value
        return True

    def delete(self, key):
        self.keys.pop(key, None)

    def exists(self, key):
        return 1 if key in self.keys else 0


@pytest.fixture
def redis(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(import_lock, "_redis", lambda: fake)
    return fake


def _candidate() -> Candidate:
    return Candidate(source="soundcloud", url=URL, title="Dashboard", duration=150, artist="BONES")


def test_second_acquire_is_refused(redis):
    assert import_lock.acquire(URL) is True
    assert import_lock.acquire(URL) is False
    import_lock.release(URL)
    assert import_lock.acquire(URL) is True


def test_without_redis_import_is_not_blocked(monkeypatch):
    monkeypatch.setattr(import_lock, "_redis", lambda: None)
    assert import_lock.acquire(URL) is True
    assert import_lock.is_locked(URL) is False


async def test_waiter_takes_the_track_of_the_first_import(session, redis, monkeypatch):
    """Ссылку уже качают — второй не качает сам, а забирает готовый трек."""
    import_lock.acquire(URL)  # «первый поток» держит замок
    monkeypatch.setattr(importer, "_FOREIGN_POLL_SECONDS", 0.01)

    calls = {"n": 0}

    async def appears_on_second_look(_session, url):
        calls["n"] += 1
        if calls["n"] < 3:
            return None
        track = Track(title="Dashboard", artist="BONES", duration=150, source_url=url, tg_file_id="F")
        return track

    monkeypatch.setattr("app.services.search.find_track_by_source_url", appears_on_second_look)

    def must_not_download(_candidate):
        raise AssertionError("второй поток не должен качать ту же ссылку")

    monkeypatch.setattr(importer, "download_with_fallback", must_not_download)
    track, created = await importer.import_candidate(
        session, bot=None, candidate=_candidate(), telegram_id=1, save_to_library=False
    )
    assert created is False and track.source_url == URL


async def test_lock_is_released_after_failed_download(session, redis, monkeypatch):
    """Упал импорт — замок снят, следующая попытка не ждёт полторы минуты."""
    monkeypatch.setattr(importer, "download_with_fallback", lambda _c: None)
    with pytest.raises(Exception):
        await importer.import_candidate(
            session, bot=None, candidate=_candidate(), telegram_id=1, save_to_library=False
        )
    assert import_lock.is_locked(URL) is False

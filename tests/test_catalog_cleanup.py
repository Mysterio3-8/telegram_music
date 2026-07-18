import pytest

from app.config import settings
from app.db.models import Lyrics, Playlist, PlaylistTrack, Track, TrackEvent, Upload, User, UserLibrary
from app.services.catalog_cleanup import count_junk_tracks, delete_junk_tracks, list_junk_tracks


@pytest.fixture
def with_duration_bounds(monkeypatch):
    """Очистка не-музыки определена только когда границы длительности заданы."""
    monkeypatch.setattr(settings, "track_min_seconds", 40)
    monkeypatch.setattr(settings, "track_max_seconds", 540)


class FakeStorage:
    def __init__(self):
        self.deleted: list[str] = []

    def save(self, key, data):
        return f"local://{key}"

    def load(self, key):
        return b""

    def delete(self, key):
        self.deleted.append(key)


async def _track(session, title, duration, storage_path=None, file_size=None) -> Track:
    track = Track(title=title, artist="A", duration=duration, storage_path=storage_path, file_size=file_size)
    session.add(track)
    await session.commit()
    return track


async def test_no_junk_when_limits_disabled(session):
    # Границы 0 (лимиты сняты) — не-музыки по длительности не существует
    await _track(session, "Джингл", 10, file_size=1000)
    await _track(session, "Подкаст", 3600, file_size=90_000_000)

    assert (await count_junk_tracks(session)).count == 0
    assert await list_junk_tracks(session) == []


async def test_count_and_list_junk(session, with_duration_bounds):
    await _track(session, "Джингл", 10, file_size=1000)
    await _track(session, "Подкаст", 3600, file_size=90_000_000)
    await _track(session, "Нормальный", 200)

    junk = await count_junk_tracks(session)
    assert junk.count == 2
    assert junk.total_bytes == 90_001_000

    titles = [t.title for t in await list_junk_tracks(session)]
    assert "Нормальный" not in titles
    assert set(titles) == {"Джингл", "Подкаст"}


async def test_delete_junk_removes_track_links_and_files(session, with_duration_bounds):
    user = User(telegram_id=1)
    session.add(user)
    await session.flush()

    junk = await _track(session, "Подкаст", 3600, storage_path="local://tracks/1")
    keep = await _track(session, "Нормальный", 200)
    playlist = Playlist(user_id=user.id, title="P")
    session.add(playlist)
    await session.flush()
    session.add(UserLibrary(user_id=user.id, track_id=junk.id))
    session.add(PlaylistTrack(playlist_id=playlist.id, track_id=junk.id, position=1))
    session.add(TrackEvent(user_id=user.id, track_id=junk.id, event="listen"))
    session.add(Lyrics(track_id=junk.id, text="слова"))
    session.add(Upload(user_id=user.id, track_id=junk.id))
    await session.commit()
    junk_id = junk.id

    storage = FakeStorage()
    deleted = await delete_junk_tracks(session, storage)

    assert deleted == 1
    assert storage.deleted == [f"tracks/{junk_id}"]
    assert await session.get(Track, junk_id) is None
    assert await session.get(Track, keep.id) is not None
    assert await session.get(UserLibrary, (user.id, junk_id)) is None
    assert await session.get(Lyrics, junk_id) is None
    assert (await count_junk_tracks(session)).count == 0


async def test_delete_junk_noop_when_clean(session):
    await _track(session, "Нормальный", 200)
    storage = FakeStorage()
    assert await delete_junk_tracks(session, storage) == 0
    assert storage.deleted == []

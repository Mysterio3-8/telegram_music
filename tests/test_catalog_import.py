import pytest
from sqlalchemy import select

from app.db.models import Instrumental, Track
from app.importers.base import ImportItem
from app.services import catalog_import
from app.storage.local import LocalStorage


@pytest.fixture
def storage(tmp_path):
    return LocalStorage(str(tmp_path))


def make_item(title="Believer", artist="Imagine Dragons", duration=200) -> ImportItem:
    return ImportItem(title=title, artist=artist, duration=duration, data=b"audio", file_format="mp3")


@pytest.fixture(autouse=True)
def no_fingerprint(monkeypatch):
    # На dev-машине нет fpcalc; фиксируем отсутствие отпечатка, дедуп идёт по метаданным
    monkeypatch.setattr(catalog_import, "compute_fingerprint_from_bytes", lambda *a, **k: None)


async def test_import_creates_track_and_stores_file(session, storage):
    created = await catalog_import.import_track(session, storage, make_item())

    assert created is True
    track = await session.get(Track, 1)
    assert track.title == "Believer"
    assert track.storage_path == "local://tracks/1"
    assert track.file_size == len(b"audio")
    assert storage.exists("tracks/1")


async def test_import_skips_metadata_duplicate(session, storage):
    await catalog_import.import_track(session, storage, make_item())

    created_again = await catalog_import.import_track(session, storage, make_item())

    assert created_again is False
    count = len((await session.scalars(select(Track))).all())
    assert count == 1


async def test_import_skips_fingerprint_duplicate(session, storage, monkeypatch):
    monkeypatch.setattr(catalog_import, "compute_fingerprint_from_bytes", lambda *a, **k: "FP1")
    await catalog_import.import_track(session, storage, make_item(title="Original"))

    # другое название/исполнитель, но тот же отпечаток → дубликат
    created = await catalog_import.import_track(
        session, storage, make_item(title="Renamed", artist="Other")
    )

    assert created is False


async def test_import_instrumental(session, storage):
    created = await catalog_import.import_instrumental(session, storage, make_item(title="Believer Minus"))

    assert created is True
    instrumental = await session.get(Instrumental, 1)
    assert instrumental.title == "Believer Minus"
    assert instrumental.storage_path == "local://instrumentals/1"

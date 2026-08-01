"""Сторож диска: чистит только производное, самый свежий бэкап не трогает."""
import pytest

from app.config import settings
from app.services import disk_guard
from app.services.disk_guard import ReclaimReport, alert_text, reclaim_disk


@pytest.fixture
def disk_dirs(tmp_path, monkeypatch):
    cache = tmp_path / "audio_cache"
    backups = tmp_path / "backups"
    cache.mkdir()
    backups.mkdir()
    monkeypatch.setattr(settings, "audio_cache_dir", str(cache))
    monkeypatch.setattr(settings, "backup_dir", str(backups))
    monkeypatch.setattr(settings, "backup_keep_low_disk", 1)
    return cache, backups


def _make_files(directory, names: list[str]) -> None:
    """Файлы с возрастающим mtime — порядок удаления должен быть от старых."""
    for index, name in enumerate(names):
        path = directory / name
        path.write_bytes(b"x")
        import os

        os.utime(path, (1000 + index, 1000 + index))


@pytest.fixture
def free_space(monkeypatch):
    """Управляемое свободное место: растёт на 100 МБ с каждым удалённым файлом."""
    state = {"mb": 0}

    monkeypatch.setattr(disk_guard, "free_mb", lambda path=".": state["mb"])
    return state


def test_does_nothing_when_space_is_plenty(disk_dirs, free_space):
    cache, _ = disk_dirs
    _make_files(cache, ["a", "b"])
    free_space["mb"] = 9000

    report = reclaim_disk(target_free_mb=3000)

    assert report.did_anything is False
    assert len(list(cache.iterdir())) == 2


def test_evicts_oldest_cache_files_first(disk_dirs, free_space, monkeypatch):
    cache, _ = disk_dirs
    _make_files(cache, ["old", "middle", "new"])
    free_space["mb"] = 1000

    # Каждое удаление «освобождает» 1100 МБ: 1000 → 2100 → 3200, порог 3000
    # перешагивается на втором файле, третий остаётся нетронутым
    original_unlink = disk_guard.Path.unlink

    def counting_unlink(self, **kwargs):
        original_unlink(self, **kwargs)
        free_space["mb"] += 1100

    monkeypatch.setattr(disk_guard.Path, "unlink", counting_unlink)

    report = reclaim_disk(target_free_mb=3000)

    assert report.removed_cache_files == 2
    assert {f.name for f in cache.iterdir()} == {"new"}


def test_keeps_newest_backup_even_when_disk_is_full(disk_dirs, free_space):
    cache, backups = disk_dirs
    _make_files(backups, ["db-1.sqlite", "db-2.sqlite", "db-3.sqlite"])
    free_space["mb"] = 100  # чистка не помогает, место не растёт

    report = reclaim_disk(target_free_mb=3000)

    assert report.removed_backups == 2
    assert {f.name for f in backups.iterdir()} == {"db-3.sqlite"}


def test_alert_is_silent_when_space_recovered(monkeypatch):
    monkeypatch.setattr(settings, "disk_alert_free_mb", 2048)
    assert alert_text(ReclaimReport(500, 5000, 10, 1)) is None


def test_alert_reports_numbers_when_still_low(monkeypatch):
    monkeypatch.setattr(settings, "disk_alert_free_mb", 2048)

    text = alert_text(ReclaimReport(300, 900, 10, 1))

    assert text is not None
    assert "900 МБ" in text
    assert "600 МБ" in text  # освободили


def test_alert_says_nothing_to_clean_when_reclaim_found_nothing(monkeypatch):
    monkeypatch.setattr(settings, "disk_alert_free_mb", 2048)

    text = alert_text(ReclaimReport(500, 500, 0, 0))

    assert "Чистить нечего" in text

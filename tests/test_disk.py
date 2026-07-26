from app.config import settings
from app.services import disk


def test_enough_free_disk_true_when_plenty(monkeypatch):
    monkeypatch.setattr(settings, "min_free_disk_mb", 1024)
    monkeypatch.setattr(disk, "free_mb", lambda path=".": 5000)
    assert disk.enough_free_disk() is True


def test_enough_free_disk_false_when_low(monkeypatch):
    monkeypatch.setattr(settings, "min_free_disk_mb", 1024)
    monkeypatch.setattr(disk, "free_mb", lambda path=".": 300)
    assert disk.enough_free_disk() is False


def test_download_soundcloud_skips_when_disk_low(monkeypatch):
    from app.services import soundcloud

    monkeypatch.setattr("app.services.disk.enough_free_disk", lambda: False)
    # диск заполнен → не качаем, возвращаем None не трогая сеть
    assert soundcloud.download_soundcloud_audio("https://soundcloud.com/x/y") is None


def test_download_audio_skips_when_disk_low(monkeypatch):
    from app.services.youtube import downloader

    monkeypatch.setattr("app.services.disk.enough_free_disk", lambda: False)
    assert downloader.download_audio("abcdef12345") is None

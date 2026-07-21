from app.config import settings
from app.services import proxies, soundcloud


def test_no_proxies_returns_none(monkeypatch):
    monkeypatch.setattr(settings, "proxy_list", "")

    assert proxies.next_proxy() is None


def test_round_robin_rotation(monkeypatch):
    monkeypatch.setattr(settings, "proxy_list", "http://a:1, http://b:2")

    got = [proxies.next_proxy() for _ in range(4)]

    assert got == ["http://a:1", "http://b:2", "http://a:1", "http://b:2"]


def test_cycle_resets_on_config_change(monkeypatch):
    monkeypatch.setattr(settings, "proxy_list", "http://a:1")
    assert proxies.next_proxy() == "http://a:1"

    monkeypatch.setattr(settings, "proxy_list", "http://c:3,http://d:4")

    assert proxies.next_proxy() == "http://c:3"


def test_download_retries_with_next_proxy(monkeypatch):
    """Ошибка через прокси → повтор; число попыток ограничено списком прокси."""
    monkeypatch.setattr(settings, "proxy_list", "http://a:1,http://b:2")
    calls = []

    def failing_download(url):
        calls.append(url)
        raise RuntimeError("proxy connection refused")

    monkeypatch.setattr(soundcloud, "_download_soundcloud_once", failing_download)

    try:
        soundcloud.download_soundcloud_audio("https://soundcloud.com/x/y")
        raise AssertionError("должно было упасть после всех попыток")
    except RuntimeError:
        pass

    assert len(calls) == 2  # по попытке на каждый прокси


def test_download_single_attempt_without_proxies(monkeypatch):
    monkeypatch.setattr(settings, "proxy_list", "")
    calls = []

    def failing_download(url):
        calls.append(url)
        raise RuntimeError("network down")

    monkeypatch.setattr(soundcloud, "_download_soundcloud_once", failing_download)

    try:
        soundcloud.download_soundcloud_audio("https://soundcloud.com/x/y")
        raise AssertionError("должно было упасть")
    except RuntimeError:
        pass

    assert len(calls) == 1

"""Ссылка боту не может увести сервер внутрь его же сети (аудит 24.09)."""
import pytest

from app.services import link_import
from app.services.link_import import is_public_url


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8011/api/users",  # веб-админка
        "http://localhost:8010/",  # API
        "http://169.254.169.254/latest/meta-data/",  # метаданные облака
        "http://10.0.0.5/",
        "http://192.168.1.1/",
        "http://[::1]/",
        "ftp://example.com/file.mp3",
        "file:///etc/passwd",
        "https://user:pass@example.com/a",
        "https://example.com:6379/",  # Redis-порт на чужой машине
    ],
)
def test_internal_or_odd_urls_are_rejected(url):
    assert is_public_url(url) is False


def test_name_resolving_to_loopback_is_rejected(monkeypatch):
    """Свой домен, указывающий на 127.0.0.1, — классический обход проверки по имени."""
    import socket

    monkeypatch.setattr(
        socket, "getaddrinfo", lambda *a, **k: [(socket.AF_INET, 1, 6, "", ("127.0.0.1", 443))]
    )
    assert is_public_url("https://evil-rebind.example/track") is False


def test_public_host_passes(monkeypatch):
    import socket

    monkeypatch.setattr(
        socket, "getaddrinfo", lambda *a, **k: [(socket.AF_INET, 1, 6, "", ("93.184.216.34", 443))]
    )
    assert is_public_url("https://bandcamp.com/track/x") is True


def test_download_refuses_internal_url_without_touching_ytdlp(monkeypatch):
    class Boom:
        def __init__(self, *_a, **_k):
            raise AssertionError("yt-dlp не должен вызываться для внутреннего адреса")

    monkeypatch.setattr(link_import.yt_dlp, "YoutubeDL", Boom)
    assert link_import.download_any("http://127.0.0.1:8011/api/users") is None
    assert link_import.list_any_entries("http://127.0.0.1:8011/") == []

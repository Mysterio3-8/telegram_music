"""Ночная проверка выходов VPN для YouTube (живой прогон 25.09)."""
from app.cli import youtube_exits


def _setup(monkeypatch, alive_set):
    alerts = []
    proxies = ["socks5://a:1", "socks5://b:2", "socks5://c:3"]
    monkeypatch.setattr(youtube_exits, "_configured_proxies", lambda: proxies)
    monkeypatch.setattr(youtube_exits, "discover_ids", lambda n, proxy: ["vid"])
    monkeypatch.setattr(youtube_exits, "probe", lambda vid, proxy: (proxy in alive_set, "", 0))
    monkeypatch.setattr(youtube_exits, "_PAUSE_SECONDS", 0)
    monkeypatch.setattr(youtube_exits, "_alert", alerts.append)
    return alerts


def test_dead_exit_among_alive_is_reported(monkeypatch):
    """Мёртвые выходы стояли первыми, и скачивание падало, а проверка молчала."""
    alerts = _setup(monkeypatch, {"socks5://b:2", "socks5://c:3"})
    assert youtube_exits.check() == 0
    assert len(alerts) == 1
    assert "socks5://a:1" in alerts[0]
    assert "YOUTUBE_PROXY=socks5://b:2,socks5://c:3" in alerts[0]


def test_all_alive_is_quiet(monkeypatch):
    alerts = _setup(monkeypatch, {"socks5://a:1", "socks5://b:2", "socks5://c:3"})
    assert youtube_exits.check() == 0
    assert alerts == []

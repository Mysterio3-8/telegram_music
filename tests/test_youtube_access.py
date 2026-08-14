"""Доступ к YouTube: прокси плюс tv_embedded (замер на проде 14.08).

С IP сервера YouTube отвечает «Sign in to confirm you're not a bot» на все
десять player-клиентов — блокировка по адресу, а не по клиенту, и свежий yt-dlp
от неё не спасает. Работает единственная связка: прокси + `tv_embedded`.
Порознь ни то ни другое не помогает: только прокси даёт 403 на медиа-URL,
только tv_embedded — тот же «Sign in».
"""
from app.config import settings
from app.services.youtube.downloader import youtube_attempt_plan, youtube_opts


def test_player_client_goes_into_extractor_args(monkeypatch):
    monkeypatch.setattr(settings, "youtube_player_client", "tv_embedded")
    opts = youtube_opts()
    assert opts["extractor_args"] == {"youtube": {"player_client": ["tv_embedded"]}}


def test_empty_client_keeps_default_behaviour(monkeypatch):
    """Пустая настройка — поведение до 14.08, без вмешательства в выбор клиента."""
    monkeypatch.setattr(settings, "youtube_player_client", "")
    assert "extractor_args" not in youtube_opts()


def test_proxy_applied_and_skipped_on_direct_attempt(monkeypatch):
    monkeypatch.setattr(settings, "youtube_proxy", "socks5://127.0.0.1:10808")
    assert youtube_opts()["proxy"] == "socks5://127.0.0.1:10808"
    # Запасной ход в обход прокси: если Xray лёг, честнее попробовать напрямую
    assert "proxy" not in youtube_opts(direct=True)


def test_no_proxy_configured_means_no_proxy_key(monkeypatch):
    monkeypatch.setattr(settings, "youtube_proxy", "")
    assert "proxy" not in youtube_opts()


def test_attempt_plan_tries_proxy_first(monkeypatch):
    """Сначала прокси, потом напрямую: прямая попытка сейчас это гарантированный
    отказ, но она осталась на случай, если прокси недоступен."""
    monkeypatch.setattr(settings, "youtube_proxy", "socks5://127.0.0.1:10808")
    assert youtube_attempt_plan() == [False, True]


def test_attempt_plan_without_proxy_is_single_direct(monkeypatch):
    monkeypatch.setattr(settings, "youtube_proxy", "")
    assert youtube_attempt_plan() == [False]


def test_soundcloud_untouched_by_youtube_proxy(monkeypatch):
    """SoundCloud через тот же прокси работает с той же скоростью (6.22 против
    6.83 сек), поэтому главный источник остаётся на прямом соединении."""
    from app.services.youtube.downloader import _base_opts

    monkeypatch.setattr(settings, "youtube_proxy", "socks5://127.0.0.1:10808")
    monkeypatch.setattr(settings, "proxy_list", "")
    assert "proxy" not in _base_opts(impersonate=True, use_proxy=True)


def test_download_falls_back_to_direct_attempt(monkeypatch):
    """Прокси не сработал — пробуем напрямую, а не сдаёмся молча."""
    from app.services.youtube import downloader

    monkeypatch.setattr(settings, "youtube_proxy", "socks5://127.0.0.1:10808")
    seen: list[bool] = []

    def fake_once(video_id, as_mp3=False, direct=False):
        seen.append(direct)
        return None

    monkeypatch.setattr(downloader, "_download_audio_once", fake_once)
    assert downloader.download_audio("abcdefghijk") is None
    assert seen == [False, True]


def test_download_stops_after_first_success(monkeypatch):
    from app.services.youtube import downloader

    monkeypatch.setattr(settings, "youtube_proxy", "socks5://127.0.0.1:10808")
    seen: list[bool] = []

    def fake_once(video_id, as_mp3=False, direct=False):
        seen.append(direct)
        return "audio"

    monkeypatch.setattr(downloader, "_download_audio_once", fake_once)
    assert downloader.download_audio("abcdefghijk") == "audio"
    assert seen == [False]  # вторая попытка не понадобилась

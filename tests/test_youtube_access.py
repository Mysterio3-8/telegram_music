"""Доступ к YouTube: прокси плюс tv_embedded (замер на проде 14.08).

С IP сервера YouTube отвечает «Sign in to confirm you're not a bot» на все
десять player-клиентов — блокировка по адресу, а не по клиенту, и свежий yt-dlp
от неё не спасает. Работает единственная связка: прокси + `tv_embedded`.
Порознь ни то ни другое не помогает: только прокси даёт 403 на медиа-URL,
только tv_embedded — тот же «Sign in».

Отдельная история — ротация выходов: отказы плавают по узлам, и трек, который
через один выход отдал 403, через соседний скачивается.
"""
import pytest

from app.config import settings
from app.services import proxies
from app.services.youtube.downloader import youtube_attempt_plan, youtube_opts

FIVE = ",".join(f"socks5://127.0.0.1:{port}" for port in range(10811, 10816))


@pytest.fixture(autouse=True)
def _reset_rotation():
    """Сдвиг ротации — глобальный на процесс; между тестами обнуляем, иначе
    порядок выходов зависел бы от того, кто отработал раньше."""
    proxies._yt_offset = 0
    yield
    proxies._yt_offset = 0


# --- клиент и прокси в настройках yt-dlp ----------------------------------------


def test_player_client_goes_into_extractor_args(monkeypatch):
    monkeypatch.setattr(settings, "youtube_player_client", "tv_embedded")
    monkeypatch.setattr(settings, "youtube_proxy", "")
    opts = youtube_opts()
    assert opts["extractor_args"] == {"youtube": {"player_client": ["tv_embedded"]}}


def test_empty_client_keeps_default_behaviour(monkeypatch):
    """Пустая настройка — поведение до 14.08, без вмешательства в выбор клиента."""
    monkeypatch.setattr(settings, "youtube_player_client", "")
    monkeypatch.setattr(settings, "youtube_proxy", "")
    assert "extractor_args" not in youtube_opts()


def test_explicit_proxy_wins(monkeypatch):
    monkeypatch.setattr(settings, "youtube_proxy", FIVE)
    assert youtube_opts(proxy="socks5://127.0.0.1:10813")["proxy"] == (
        "socks5://127.0.0.1:10813"
    )


def test_explicit_none_means_direct(monkeypatch):
    """Запасной ход: если Xray лёг, честнее попробовать напрямую и получить
    внятный отказ, чем молчать."""
    monkeypatch.setattr(settings, "youtube_proxy", FIVE)
    assert "proxy" not in youtube_opts(proxy=None)


def test_default_takes_next_exit_from_rotation(monkeypatch):
    monkeypatch.setattr(settings, "youtube_proxy", FIVE)
    assert youtube_opts()["proxy"] == "socks5://127.0.0.1:10811"


def test_no_proxy_configured_means_no_proxy_key(monkeypatch):
    monkeypatch.setattr(settings, "youtube_proxy", "")
    assert "proxy" not in youtube_opts()


# --- ротация выходов -------------------------------------------------------------


def test_chain_tries_several_distinct_exits_then_direct(monkeypatch):
    monkeypatch.setattr(settings, "youtube_proxy", FIVE)
    monkeypatch.setattr(settings, "youtube_proxy_attempts", 3)

    chain = youtube_attempt_plan()
    assert chain[-1] is None, "последней обязана быть прямая попытка"
    exits = chain[:-1]
    assert len(exits) == 3
    assert len(set(exits)) == 3, "выходы обязаны быть РАЗНЫМИ, иначе перебор бесполезен"


def test_chain_shifts_start_between_calls(monkeypatch):
    """Иначе весь трафик шёл бы через один узел: он первым получил бы репутацию
    бота, а остальные четыре стояли бы без дела до его смерти."""
    monkeypatch.setattr(settings, "youtube_proxy", FIVE)
    monkeypatch.setattr(settings, "youtube_proxy_attempts", 2)

    first = youtube_attempt_plan()[0]
    second = youtube_attempt_plan()[0]
    third = youtube_attempt_plan()[0]
    assert first != second != third


def test_chain_wraps_around_the_list(monkeypatch):
    """Сдвиг не должен уезжать за край списка."""
    monkeypatch.setattr(settings, "youtube_proxy", FIVE)
    monkeypatch.setattr(settings, "youtube_proxy_attempts", 3)

    for _ in range(12):  # больше, чем выходов
        chain = youtube_attempt_plan()
        assert all(p in settings.youtube_proxy_items for p in chain[:-1])


def test_attempts_capped_by_available_exits(monkeypatch):
    """Просить больше попыток, чем есть выходов, нельзя — получились бы повторы
    по тому же узлу, то есть трата секунд человека впустую."""
    monkeypatch.setattr(settings, "youtube_proxy", "socks5://127.0.0.1:10811")
    monkeypatch.setattr(settings, "youtube_proxy_attempts", 5)

    chain = youtube_attempt_plan()
    assert chain == ["socks5://127.0.0.1:10811", None]


def test_without_proxy_single_direct_attempt(monkeypatch):
    monkeypatch.setattr(settings, "youtube_proxy", "")
    assert youtube_attempt_plan() == [None]


# --- SoundCloud не задет ----------------------------------------------------------


def test_soundcloud_untouched_by_youtube_proxy(monkeypatch):
    """SoundCloud через тот же VPN идёт с той же скоростью (6.22 против 6.83
    сек), поэтому главный источник остаётся на прямом соединении."""
    from app.services.youtube.downloader import _base_opts

    monkeypatch.setattr(settings, "youtube_proxy", FIVE)
    monkeypatch.setattr(settings, "proxy_list", "")
    assert "proxy" not in _base_opts(impersonate=True, use_proxy=True)


# --- перебор при скачивании --------------------------------------------------------


def test_download_walks_the_whole_chain(monkeypatch):
    from app.services.youtube import downloader

    monkeypatch.setattr(settings, "youtube_proxy", FIVE)
    monkeypatch.setattr(settings, "youtube_proxy_attempts", 3)
    seen: list[str | None] = []

    def fake_once(video_id, as_mp3=False, proxy=None):
        seen.append(proxy)
        return None

    monkeypatch.setattr(downloader, "_download_audio_once", fake_once)
    assert downloader.download_audio("abcdefghijk") is None
    assert len(seen) == 4 and seen[-1] is None


def test_download_stops_after_first_success(monkeypatch):
    from app.services.youtube import downloader

    monkeypatch.setattr(settings, "youtube_proxy", FIVE)
    monkeypatch.setattr(settings, "youtube_proxy_attempts", 3)
    seen: list[str | None] = []

    def fake_once(video_id, as_mp3=False, proxy=None):
        seen.append(proxy)
        return "audio"

    monkeypatch.setattr(downloader, "_download_audio_once", fake_once)
    assert downloader.download_audio("abcdefghijk") == "audio"
    assert len(seen) == 1, "лишние попытки — это лишние секунды ожидания человека"

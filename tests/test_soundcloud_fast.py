"""Быстрое скачивание с SoundCloud напрямую (21.09): 0,5 сек против 7,0 у yt-dlp."""
from app.services import soundcloud_fast
from app.services.soundcloud_fast import fast_download

PROGRESSIVE = {
    "kind": "track",
    "id": 2076192488,
    "title": "Fake ID",
    "full_duration": 225000,
    "artwork_url": "https://i1.sndcdn.com/a-large.jpg",
    "user": {"username": "kizaru_hf"},
    "publisher_metadata": {"artist": "kizaru", "album_title": "BORN TO TRAP"},
    "media": {
        "transcodings": [
            {"url": "https://api-v2.soundcloud.com/media/hls", "format": {"protocol": "hls", "mime_type": "audio/mpeg"}},
            {"url": "https://api-v2.soundcloud.com/media/prog", "format": {"protocol": "progressive", "mime_type": "audio/mpeg"}},
        ]
    },
}


def _api(responses):
    calls = []

    def fake(path, params=None):
        calls.append(path)
        return responses.get(path)

    return fake, calls


def test_progressive_track_downloads_without_ytdlp(monkeypatch):
    fake, calls = _api({"/resolve": PROGRESSIVE, "/media/prog": {"url": "https://cf/stream.mp3"}})
    monkeypatch.setattr("app.services.soundcloud_api.api_get", fake)
    monkeypatch.setattr(soundcloud_fast, "_fetch_bytes", lambda _url: b"ID3" + b"\x00" * 100)

    audio = fast_download("https://soundcloud.com/kizaru_hf/fake-id")
    assert audio is not None
    assert audio.file_format == "mp3" and audio.duration == 225
    assert audio.video_title == "Fake ID" and audio.uploader == "kizaru"
    # 🔴 artwork_url у SoundCloud — это «-large», 100×100 и 4 КБ. Быстрый путь
    # вшивал в файл именно её («картинки в ужасном качестве», 21.09), поэтому
    # апскейлим к t500x500 — тот же CDN, другой суффикс.
    assert audio.album == "BORN TO TRAP" and audio.thumbnail_url.endswith("a-t500x500.jpg")
    assert "/media/prog" in calls


def test_hls_only_falls_back_to_ytdlp(monkeypatch):
    only_hls = {**PROGRESSIVE, "media": {"transcodings": [
        {"url": "https://api-v2.soundcloud.com/media/hls", "format": {"protocol": "hls", "mime_type": "audio/mpeg"}},
    ]}}
    fake, _ = _api({"/resolve": only_hls, "/tracks/2076192488": only_hls})
    monkeypatch.setattr("app.services.soundcloud_api.api_get", fake)
    assert fast_download("https://soundcloud.com/k/t") is None


def test_search_card_is_completed_by_full_track(monkeypatch):
    # У карточки из поиска список вариантов бывает урезан — добираем /tracks/{id}
    trimmed = {**PROGRESSIVE, "media": {"transcodings": []}}
    fake, calls = _api({
        "/resolve": trimmed,
        "/tracks/2076192488": PROGRESSIVE,
        "/media/prog": {"url": "https://cf/stream.mp3"},
    })
    monkeypatch.setattr("app.services.soundcloud_api.api_get", fake)
    monkeypatch.setattr(soundcloud_fast, "_fetch_bytes", lambda _url: b"ID3")
    assert fast_download("https://soundcloud.com/k/t") is not None
    assert "/tracks/2076192488" in calls


def test_playlist_link_is_not_our_path(monkeypatch):
    fake, _ = _api({"/resolve": {"kind": "playlist"}})
    monkeypatch.setattr("app.services.soundcloud_api.api_get", fake)
    assert fast_download("https://soundcloud.com/k/sets/album") is None


def test_api_failure_is_silent(monkeypatch):
    def boom(*_args, **_kwargs):
        raise RuntimeError("API лёг")

    monkeypatch.setattr("app.services.soundcloud_api.api_get", boom)
    assert fast_download("https://soundcloud.com/k/t") is None


def test_empty_download_falls_back(monkeypatch):
    fake, _ = _api({"/resolve": PROGRESSIVE, "/media/prog": {"url": "https://cf/stream.mp3"}})
    monkeypatch.setattr("app.services.soundcloud_api.api_get", fake)
    monkeypatch.setattr(soundcloud_fast, "_fetch_bytes", lambda _url: None)
    assert fast_download("https://soundcloud.com/k/t") is None

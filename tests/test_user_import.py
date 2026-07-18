from app.config import settings
from app.services.youtube.user_import import duration_error, extract_video_id, is_playlist_link


def test_extract_video_id_formats():
    cases = {
        "https://youtu.be/dQw4w9WgXcQ": "dQw4w9WgXcQ",
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ": "dQw4w9WgXcQ",
        "https://www.youtube.com/watch?feature=share&v=dQw4w9WgXcQ": "dQw4w9WgXcQ",
        "https://youtube.com/shorts/dQw4w9WgXcQ": "dQw4w9WgXcQ",
        "https://music.youtube.com/watch?v=dQw4w9WgXcQ&list=RD1": "dQw4w9WgXcQ",
        "https://www.youtube.com/embed/dQw4w9WgXcQ": "dQw4w9WgXcQ",
        "посмотри https://youtu.be/dQw4w9WgXcQ круто": "dQw4w9WgXcQ",
    }
    for url, expected in cases.items():
        assert extract_video_id(url) == expected, url


def test_extract_video_id_rejects_non_video():
    assert extract_video_id("просто текст") is None
    assert extract_video_id("https://example.com/watch?v=dQw4w9WgXcQ") is None
    assert extract_video_id("https://www.youtube.com/@somechannel") is None
    assert extract_video_id("https://www.youtube.com/playlist?list=PL123") is None


def test_is_playlist_link():
    assert is_playlist_link("https://www.youtube.com/playlist?list=PL123") is True
    assert is_playlist_link("https://youtube.com/@somechannel") is True
    assert is_playlist_link("https://www.youtube.com/channel/UC123") is True
    assert is_playlist_link("https://www.youtube.com/c/OldStyle") is True
    assert is_playlist_link("https://youtu.be/dQw4w9WgXcQ") is False
    assert is_playlist_link("просто текст") is False
    # watch-ссылка с list= — тоже плейлистная (но extract_video_id проверяется раньше:
    # одиночное видео из плейлиста импортируется как одно видео)
    assert is_playlist_link("https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=RD1") is True
    assert extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=RD1") == "dQw4w9WgXcQ"


def test_duration_no_limits_by_default():
    # Владелец снял лимиты (track_min/max_seconds = 0) — любая длительность проходит
    assert duration_error(1) is None
    assert duration_error(10_000) is None


def test_duration_limits_when_configured(monkeypatch):
    monkeypatch.setattr(settings, "track_min_seconds", 40)
    monkeypatch.setattr(settings, "track_max_seconds", 540)

    assert duration_error(200) is None
    too_short = duration_error(39)
    assert too_short is not None and "короткое" in too_short
    too_long = duration_error(541)
    assert too_long is not None and "подкаст" in too_long


def test_extract_video_id_youtube_music():
    from app.services.youtube.user_import import extract_video_id, is_playlist_link

    assert extract_video_id("https://music.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert is_playlist_link("https://music.youtube.com/playlist?list=PLabc")
    assert is_playlist_link("https://music.youtube.com/channel/UCabcdef")


def test_normalize_source_url_youtube_music():
    from app.services.youtube.downloader import normalize_source_url

    assert (
        normalize_source_url("https://music.youtube.com/playlist?list=PLabc")
        == "https://www.youtube.com/playlist?list=PLabc"
    )
    assert (
        normalize_source_url("https://music.youtube.com/channel/UCabc")
        == "https://www.youtube.com/channel/UCabc/videos"
    )

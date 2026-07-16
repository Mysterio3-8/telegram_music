from app.config import settings
from app.services.youtube.user_import import duration_error, extract_video_id


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


def test_duration_limits():
    assert duration_error(settings.track_min_seconds) is None
    assert duration_error(settings.track_max_seconds) is None
    assert duration_error(200) is None

    too_short = duration_error(settings.track_min_seconds - 1)
    assert too_short is not None and "короткое" in too_short

    too_long = duration_error(settings.track_max_seconds + 1)
    assert too_long is not None and "подкаст" in too_long

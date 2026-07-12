import pytest

from app.services.youtube.metadata import parse_title


@pytest.mark.parametrize(
    "video_title, expected_artist, expected_title",
    [
        ("DJ KL - Акап (Official Audio)", "DJ KL", "Акап"),
        ("DJ KL — Акап", "DJ KL", "Акап"),
        ("DJ KL – Акап", "DJ KL", "Акап"),
        ("Artist - Song (Official Video)", "Artist", "Song"),
        ("Artist - Song [Lyrics]", "Artist", "Song"),
        ("Исполнитель - Трек (Премьера)", "Исполнитель", "Трек"),
        ("Big Baby Tape - Gimme the Loot (prod. Aarne)", "Big Baby Tape", "Gimme the Loot (prod. Aarne)"),
    ],
)
def test_parse_splits_and_cleans(video_title, expected_artist, expected_title):
    artist, title = parse_title(video_title, fallback_artist="Channel")
    assert artist == expected_artist
    assert title == expected_title


def test_no_separator_uses_fallback_artist():
    artist, title = parse_title("Просто Название Трека", fallback_artist="Мой Канал")
    assert artist == "Мой Канал"
    assert title == "Просто Название Трека"


def test_strips_technical_tokens_without_separator():
    artist, title = parse_title("Some Track Official Audio", fallback_artist="Ch")
    assert artist == "Ch"
    assert title == "Some Track"


def test_empty_fallback_becomes_unknown():
    artist, _ = parse_title("Track", fallback_artist="")
    assert artist == "Unknown"

"""Разбор названий минусов с YouTube — на реальных строках канала владельца."""
from app.services.minus_title import clean_minus_title, looks_like_minus, parse_minus_title


def test_parses_real_channel_titles():
    cases = [
        ("МИНУС - Lida – пупы шмупы (poopu shmupi) Lyrics (Instrumental) #music",
         ("Lida", "пупы шмупы")),
        ("МИНУС - Aarne, Платина - На бумере (Instrumental) #music",
         ("Aarne, Платина", "На бумере")),
        ("МИНУС - Егор Крид (Egor Kreed) – Malo 2.0 Клип (Instrumental) #music",
         ("Егор Крид", "Malo 2.0")),
        ("МИНУС - Pussykiller-клыки (Instrumental) #music",
         ("Pussykiller", "клыки")),
        ("МИНУС - Джизус-12 июня 1997 (Instrumental) #music",
         ("Джизус", "12 июня 1997")),
    ]
    for raw, expected in cases:
        assert parse_minus_title(raw) == expected, raw


def test_prefix_and_noise_are_stripped():
    cleaned = clean_minus_title("МИНУС - LOVV66 - БУДУ ДЕЛАТЬ (Instrumental) #music")
    assert "МИНУС" not in cleaned
    assert "Instrumental" not in cleaned
    assert "#music" not in cleaned


def test_without_dash_artist_is_not_invented():
    """Пол-названия в исполнители записывать нельзя — честнее «Неизвестный»."""
    artist, title = parse_minus_title("МИНУС - какая то длинная строка без тире")
    assert artist == "Неизвестный"
    assert title == "какая то длинная строка без тире"


def test_recognises_minus_by_title():
    assert looks_like_minus("МИНУС - Kizaru - Fake ID (Instrumental)")
    assert looks_like_minus("Kizaru - Fake ID (Instrumental)")
    assert not looks_like_minus("Kizaru - Fake ID (Official Video)")

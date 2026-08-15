"""Исполнитель у кандидатов YouTube — разбором заголовка, а не имени канала.

Замер 14.08 показал в выдаче «? — Kizaru - FAKE ID ❤️»: артист пуст, потому что
у YouTube он никогда не заполнялся, а весь заголовок целиком уезжал в название.
Человек видел в кнопке «Исполнитель — Kizaru - FAKE ID ❤️».
"""
from app.services.track_lookup.providers import (
    _youtube_candidate,
    looks_like_music,
    youtube_candidate_fields,
)
from app.services.track_lookup.ranking import Candidate


class _Entry:
    def __init__(self, title, uploader="", video_id="abcdefghijk", duration=200, cover_url=""):
        self.title = title
        self.uploader = uploader
        self.video_id = video_id
        self.duration = duration
        self.cover_url = cover_url


def test_artist_parsed_from_title():
    assert youtube_candidate_fields("Kizaru - FAKE ID") == ("Kizaru", "FAKE ID")
    assert youtube_candidate_fields("The Weeknd - Blinding Lights") == (
        "The Weeknd", "Blinding Lights",
    )


def test_title_without_separator_keeps_empty_artist():
    """Выдумывать исполнителя не из чего — лучше пусто, чем неправда."""
    artist, title = youtube_candidate_fields("БОЛЬШОЙ ВАЙБ 2026")
    assert artist is None
    assert title == "БОЛЬШОЙ ВАЙБ 2026"


def test_channel_name_never_becomes_artist():
    """У YouTube канал — это заливщик («GOLDEN SOUND», «Sueta music»), а не
    артист. Пусти мы его в artist, один трек считался бы двумя при дедупе с
    SoundCloud."""
    candidate = _youtube_candidate(_Entry("Плачь, но не звони", uploader="GOLDEN SOUND"))
    assert candidate.artist is None
    assert candidate.uploader == "GOLDEN SOUND"


def test_candidate_gets_both_fields():
    candidate = _youtube_candidate(_Entry("MACAN - Плачь, но не звони", uploader="GOLDEN SOUND"))
    assert candidate.artist == "MACAN"
    assert candidate.title == "Плачь, но не звони"


def test_music_filter_survives_the_parsing():
    """⚠️ Фильтр «похоже на музыку» искал « - » в названии, а разбор это тире
    срезает. Не поправь мы условие — YouTube выпал бы из выдачи целиком."""
    parsed = _youtube_candidate(_Entry("Kizaru - FAKE ID", uploader="defect"))
    assert " - " not in parsed.title  # тире срезано разбором
    assert looks_like_music(parsed)  # и всё же это музыка


def test_topic_channel_still_counts_as_music():
    candidate = _youtube_candidate(_Entry("Yamakasi", uploader="Miyagi & Andy Panda - Topic"))
    assert looks_like_music(candidate)
    assert candidate.official


def test_random_video_still_rejected():
    junk = Candidate(
        source="youtube", url="https://x", title="Как я провёл лето влог", duration=300,
        uploader="Вася",
    )
    assert not looks_like_music(junk)

import io

import mutagen

from app.services.track_meta import MAX_FILENAME_LENGTH, build_filename, retag_audio

# Минимальный валидный MP3: кадры MPEG-1 Layer III 128kbps 44.1kHz
MP3_FRAME = b"\xff\xfb\x90\x64" + b"\x00" * 413
MP3_BYTES = MP3_FRAME * 4


def test_filename_format_artist_dash_title():
    assert build_filename("MIA BOYKA", "ЭКСПОНАТ", "mp3") == "MIA BOYKA — ЭКСПОНАТ.mp3"


def test_filename_defaults_to_mp3_and_strips_forbidden_chars():
    name = build_filename('AC/DC: "Best"', "Back\\in|Black?", None)
    assert name == "ACDC Best — BackinBlack.mp3"


def test_filename_never_empty_and_bounded():
    assert build_filename("???", "***", "ogg") == "track.ogg"
    long_name = build_filename("A" * 200, "B" * 200, "mp3")
    assert len(long_name) <= MAX_FILENAME_LENGTH + len(".mp3")


def test_retag_writes_new_tags_into_mp3():
    result = retag_audio(MP3_BYTES, "mp3", "Новое название", "Новый исполнитель")

    audio = mutagen.File(io.BytesIO(result), easy=True)
    assert audio["title"] == ["Новое название"]
    assert audio["artist"] == ["Новый исполнитель"]


def test_retag_overwrites_existing_tags():
    tagged = retag_audio(MP3_BYTES, "mp3", "Старое", "Кто-то")
    result = retag_audio(tagged, "mp3", "Новое", "Артист")

    audio = mutagen.File(io.BytesIO(result), easy=True)
    assert audio["title"] == ["Новое"]
    assert audio["artist"] == ["Артист"]


def test_retag_returns_original_bytes_on_garbage():
    garbage = b"definitely not audio at all"
    assert retag_audio(garbage, "mp3", "T", "A") == garbage

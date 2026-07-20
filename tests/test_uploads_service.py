from app.db.models import Track, Upload, User, UserLibrary
from app.services.uploads import (
    AudioMeta,
    create_uploaded_track,
    detect_format,
    find_duplicate,
    validate_audio,
)

GOOD_META = AudioMeta(
    file_id="FILE123",
    file_name="song.mp3",
    mime_type="audio/mpeg",
    file_size=4_000_000,
    duration=200,
)


def test_detect_format_by_extension_and_mime():
    assert detect_format("track.FLAC", None) == "flac"
    assert detect_format(None, "audio/mpeg") == "mp3"
    assert detect_format("track.exe", "video/mp4") is None


def test_validate_audio_accepts_good_file():
    assert validate_audio(GOOD_META) is None


def test_validate_audio_rejects_unsupported_format():
    meta = AudioMeta("id", "virus.exe", "application/octet-stream", 1000, 100)
    assert "формат" in validate_audio(meta).lower()


def test_validate_audio_accepts_large_file():
    # Аудиофайлы без ограничения по размеру (решение владельца)
    meta = AudioMeta("id", "big.mp3", "audio/mpeg", 500 * 1024 * 1024, 100)
    assert validate_audio(meta) is None


def test_validate_audio_rejects_zero_duration():
    meta = AudioMeta("id", "song.mp3", "audio/mpeg", 1000, 0)
    assert validate_audio(meta) is not None


async def test_find_duplicate_case_insensitive_with_duration_tolerance(session):
    session.add(Track(title="Believer", artist="Imagine Dragons", duration=204))
    await session.commit()

    close = await find_duplicate(session, "BELIEVER", "imagine dragons", 205)
    far = await find_duplicate(session, "Believer", "Imagine Dragons", 250)
    other_artist = await find_duplicate(session, "Believer", "Someone", 204)

    assert close is not None
    assert far is None
    assert other_artist is None


async def test_create_uploaded_track_fills_base_upload_and_library(session):
    user = User(telegram_id=1)
    session.add(user)
    await session.commit()

    track = await create_uploaded_track(session, user.id, GOOD_META, " Believer ", "Imagine Dragons")

    assert track.title == "Believer"
    assert track.tg_file_id == "FILE123"
    assert track.storage_path is None
    assert track.format == "mp3"
    assert track.bitrate == round(4_000_000 * 8 / 200 / 1000)
    assert await session.get(UserLibrary, (user.id, track.id)) is not None
    uploads = (await session.execute(
        Upload.__table__.select().where(Upload.user_id == user.id)
    )).all()
    assert len(uploads) == 1

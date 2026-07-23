import io

from app.services.artist_entities import get_artist_by_name, upsert_artist
from app.services.track_meta import embed_cover

# APIC хранит байты как есть, mutagen их не валидирует — достаточно JPEG-сигнатуры
_JPEG = b"\xff\xd8\xff\xe0" + b"fake-jpeg-payload"


def _make_mp3() -> bytes:
    """Минимальный валидный MP3-фрейм без тегов."""
    frame = bytes.fromhex("fffb9064") + b"\x00" * 413
    return frame * 4


def test_embed_cover_mp3_roundtrip():
    from mutagen.id3 import ID3

    data = _make_mp3()

    with_cover = embed_cover(data, "mp3", _JPEG)

    assert with_cover != data
    tags = ID3(io.BytesIO(with_cover))
    apics = tags.getall("APIC")
    assert len(apics) == 1
    assert apics[0].data == _JPEG


def test_embed_cover_empty_image_is_noop():
    data = _make_mp3()

    assert embed_cover(data, "mp3", b"") == data


def test_embed_cover_unknown_format_keeps_bytes():
    assert embed_cover(b"not-audio", "ogg", _JPEG) == b"not-audio"


async def test_upsert_artist_dedupes_by_normalized_name(session):
    first, created1 = await upsert_artist(
        session, "Big Baby Tape", soundcloud_url="https://soundcloud.com/bigbabytape"
    )
    second, created2 = await upsert_artist(session, "  big baby tape ")

    assert created1 is True
    assert created2 is False
    assert first.id == second.id


async def test_upsert_fills_missing_fields_only(session):
    await upsert_artist(session, "Kizaru", soundcloud_url="https://soundcloud.com/kizaru")

    artist, _ = await upsert_artist(
        session, "Kizaru",
        soundcloud_url="https://soundcloud.com/other",  # уже есть — не перетирается
        photo_url="https://img/av.jpg",  # пусто — заполняется
    )

    assert artist.soundcloud_url == "https://soundcloud.com/kizaru"
    assert artist.photo_url == "https://img/av.jpg"


async def test_get_artist_by_name_case_insensitive(session):
    await upsert_artist(session, "OG BUDA")

    assert await get_artist_by_name(session, "og buda") is not None

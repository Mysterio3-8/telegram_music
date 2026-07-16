from app.db.models import Track
from app.services.lyrics import get_or_fetch_lyrics, get_stored_lyrics, save_lyrics


async def _track(session) -> Track:
    track = Track(title="Song", artist="Artist", duration=200)
    session.add(track)
    await session.commit()
    return track


async def test_save_and_get_lyrics(session):
    track = await _track(session)

    row = await save_lyrics(session, track.id, "Строка 1\nСтрока 2", source="user")
    assert row.source == "user"

    stored = await get_stored_lyrics(session, track.id)
    assert stored is not None
    assert "Строка 1" in stored.text


async def test_save_lyrics_updates_existing(session):
    track = await _track(session)
    await save_lyrics(session, track.id, "старый", source="lrclib")
    await save_lyrics(session, track.id, "новый", source="user")

    stored = await get_stored_lyrics(session, track.id)
    assert stored.text == "новый"
    assert stored.source == "user"


async def test_get_or_fetch_returns_stored_without_network(session):
    track = await _track(session)
    await save_lyrics(session, track.id, "закэшировано", source="user")

    # текст уже в БД — LRCLIB не запрашивается
    result = await get_or_fetch_lyrics(session, track)
    assert result.found is True
    assert result.text == "закэшировано"
    assert result.source == "user"

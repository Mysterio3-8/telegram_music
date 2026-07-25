import pytest

from app.db.models import Artist, Playlist, Track, User
from app.services.search import search_all


@pytest.mark.asyncio
async def test_search_all_sections(session):
    user = User(telegram_id=1)
    artist = Artist(name="Big Baby Tape", normalized_name="big baby tape", photo_url="p")
    session.add_all([user, artist])
    await session.commit()
    session.add_all([
        Track(title="Gimme the Loot", artist="Big Baby Tape", album="Dragonborn", duration=120),
        Track(title="Other", artist="Big Baby Tape", album="Dragonborn", duration=110),
        Track(title="Unrelated", artist="Someone", duration=100),
    ])
    session.add(Playlist(user_id=user.id, title="Big Baby Mix"))
    await session.commit()

    res = await search_all(session, "big baby")
    assert any(a.name == "Big Baby Tape" for a in res.artists)
    assert res.artists[0].photo_url == "p"  # сущность с фото первой
    assert res.albums and res.albums[0].name == "Dragonborn" and res.albums[0].track_count == 2
    assert any(p.title == "Big Baby Mix" for p in res.playlists)
    assert any(t.title == "Gimme the Loot" for t in res.tracks)


@pytest.mark.asyncio
async def test_search_all_empty_query(session):
    res = await search_all(session, "   ")
    assert res.artists == [] and res.albums == [] and res.tracks == []


@pytest.mark.asyncio
async def test_search_artists_fallback_to_tracks(session):
    """Исполнитель без сущности Artist находится по треку. ASCII — на dev-SQLite
    ilike кириллицу не понижает (грабля CLAUDE.md); на PostgreSQL-проде работает."""
    session.add(Track(title="X", artist="Noname Brothers", duration=100))
    await session.commit()
    res = await search_all(session, "noname")
    assert [a.name for a in res.artists] == ["Noname Brothers"]

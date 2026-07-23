import pytest

from app.db.models import Artist, Track, TrackEvent, User
from app.services.artist_card import get_artist_card
from app.services.genres import seed_genres, set_artist_genres


@pytest.mark.asyncio
async def test_card_without_entity_lives_on_tracks(session):
    session.add(Track(title="Solo", artist="Nobody Known", duration=100))
    await session.commit()
    card = await get_artist_card(session, "  nobody known ")
    assert card.name == "nobody known"
    assert card.track_count == 1
    assert [t.title for t in card.top_tracks] == ["Solo"]
    assert card.genres == [] and card.albums == []


@pytest.mark.asyncio
async def test_card_full(session):
    await seed_genres(session)
    artist = Artist(
        name="Big Baby Tape",
        normalized_name="big baby tape",
        photo_url="http://p/1.jpg",
        banner_url="http://b/1.jpg",
        country="RU",
        description="Рэпер",
    )
    session.add(artist)
    user = User(telegram_id=1)
    session.add(user)
    await session.commit()
    await set_artist_genres(session, artist.id, ["Trap", "Русский рэп"])

    hit = Track(title="Gimme", artist="Big Baby Tape", album="Dragonborn", duration=120,
                cover_url="http://c/1.jpg")
    other = Track(title="B-Side", artist="Big Baby Tape", album="Dragonborn", duration=110)
    session.add_all([hit, other])
    await session.commit()
    session.add(TrackEvent(user_id=user.id, track_id=hit.id, event="listen"))
    await session.commit()

    card = await get_artist_card(session, "big baby tape")
    assert card.country == "RU" and card.banner_url == "http://b/1.jpg"
    assert sorted(card.genres) == ["Trap", "Русский рэп"]
    assert card.track_count == 2
    assert card.top_tracks[0].id == hit.id  # прослушанный выше свежего
    assert len(card.top_tracks) == 2
    assert card.albums[0].name == "Dragonborn" and card.albums[0].track_count == 2
    assert card.albums[0].cover_url == "http://c/1.jpg"

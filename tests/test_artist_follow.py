import pytest

from app.db.models import Artist, Track, User
from app.services.artist_card import get_artist_card
from app.services.artist_follow import (
    followed_artists,
    follow_artist,
    is_following,
    similar_artists,
    unfollow_artist,
)
from app.services.genres import seed_genres, set_artist_genres


@pytest.mark.asyncio
async def test_follow_unfollow_and_list(session):
    user = User(telegram_id=1)
    a1 = Artist(name="Kizaru", normalized_name="kizaru", photo_url="p1")
    a2 = Artist(name="Aarne", normalized_name="aarne")
    session.add_all([user, a1, a2])
    await session.commit()
    session.add(Track(title="T", artist="Kizaru", duration=100, artist_id=a1.id))
    await session.commit()

    assert await follow_artist(session, user.id, a1.id) is True
    assert await follow_artist(session, user.id, a1.id) is False  # уже подписан
    assert await follow_artist(session, user.id, a2.id) is True
    assert await is_following(session, user.id, a1.id) is True

    followed = await followed_artists(session, user.id)
    assert {f.name for f in followed} == {"Kizaru", "Aarne"}
    kizaru = next(f for f in followed if f.name == "Kizaru")
    assert kizaru.track_count == 1 and kizaru.photo_url == "p1"

    await unfollow_artist(session, user.id, a1.id)
    assert await is_following(session, user.id, a1.id) is False
    assert {f.name for f in await followed_artists(session, user.id)} == {"Aarne"}


@pytest.mark.asyncio
async def test_similar_by_shared_genre_then_country(session):
    await seed_genres(session)
    target = Artist(name="A", normalized_name="a", country="RU")
    genre_mate = Artist(name="B", normalized_name="b", country="US")
    countryman = Artist(name="C", normalized_name="c", country="RU")
    stranger = Artist(name="D", normalized_name="d", country="US")
    session.add_all([target, genre_mate, countryman, stranger])
    await session.commit()
    await set_artist_genres(session, target.id, ["Trap"])
    await set_artist_genres(session, genre_mate.id, ["Trap"])

    similar = await similar_artists(session, target, limit=10)
    names = [s.name for s in similar]
    assert names[0] == "B"  # общий жанр — первый
    assert "C" in names  # земляк добирается
    assert "D" not in names  # ни жанра, ни страны


@pytest.mark.asyncio
async def test_card_latest_release_and_singles(session):
    artist = Artist(name="X", normalized_name="x")
    session.add(artist)
    await session.commit()
    session.add_all([
        Track(title="Old album track", artist="X", album="LP", duration=100, artist_id=artist.id),
        Track(title="Single one", artist="X", duration=100, artist_id=artist.id),
        Track(title="Newest single", artist="X", duration=100, artist_id=artist.id),
    ])
    await session.commit()

    card = await get_artist_card(session, "X")
    assert card.latest_release.title == "Newest single"  # свежий по id
    assert [t.title for t in card.singles] == ["Newest single", "Single one"]  # без альбома
    assert card.albums[0].name == "LP"

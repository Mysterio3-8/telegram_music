"""Карточки артистам, которых каталог не узнавал (владелец 22.09).

Живые строки — из прода 24.09: «ChiefKeef» (559 треков без карточки),
«smokepurpp (Purpp)», «Miyagi & Эндшпиль».
"""
import json

from sqlalchemy import select

from app.db.models import Artist, Track
from app.services import artist_resolve
from app.services.artist_resolve import clean_name, compact, primary_artist, same_artist


def test_uploader_handles_are_cleaned():
    assert clean_name("smokepurpp (Purpp)") == "smokepurpp"
    assert clean_name("unki (@unkiplug)") == "unki"
    assert clean_name("Парк Горького(Gorky Park)") == "Парк Горького"


def test_duet_goes_to_first_artist():
    assert primary_artist("Miyagi & Эндшпиль") == "Miyagi"
    assert primary_artist("Artik & Anna Asti") == "Artik"
    assert primary_artist("Smokepurpp & Murda Beatz") == "Smokepurpp"
    assert primary_artist("Kizaru feat. Big Baby Tape") == "Kizaru"


def test_handle_without_spaces_is_the_same_artist():
    assert compact("ChiefKeef") == compact("Chief Keef")
    assert same_artist("playboicarti", "Playboi Carti")
    assert same_artist("A$AP Rocky", "A$AP Rocky")


def test_similar_but_different_names_are_not_merged():
    """Урок прогрева 21.09: «МакSим» — не «Maksim Dark»."""
    assert not same_artist("МакSим", "Maksim Dark")
    assert not same_artist("Би-2", "2z ft. Young H, Black Bi")


async def _tracks(session, artist: str, count: int) -> None:
    session.add_all(
        Track(title=f"{artist} {i}", artist=artist, duration=180) for i in range(count)
    )
    await session.commit()


async def test_new_card_gets_canonical_name_and_photo(session):
    await _tracks(session, "ChiefKeef", 5)

    def lookup(name):
        assert name == "ChiefKeef"
        return {"id": 42, "name": "Chief Keef", "picture_xl": "https://e-cdns/keef.jpg"}

    report = await artist_resolve.resolve_unbound(session, lookup=lookup)
    artist = await session.scalar(select(Artist))
    assert artist.name == "Chief Keef"
    assert artist.photo_url == "https://e-cdns/keef.jpg"
    assert "ChiefKeef" in json.loads(artist.aliases)
    assert report.created_with_photo == 1 and report.tracks_bound == 5
    unbound = await session.scalar(select(Track).where(Track.artist_id.is_(None)))
    assert unbound is None
    # Строку файла не трогаем — она основа поиска и дедупа
    track = await session.scalar(select(Track))
    assert track.artist == "ChiefKeef"


async def test_existing_card_is_reused_not_duplicated(session):
    session.add(Artist(name="Miyagi", normalized_name="miyagi"))
    await session.commit()
    await _tracks(session, "Miyagi & Эндшпиль", 4)

    report = await artist_resolve.resolve_unbound(session, lookup=lambda _n: None)
    assert report.bound_existing == 1 and report.tracks_bound == 4
    artists = (await session.scalars(select(Artist))).all()
    assert len(artists) == 1


async def test_rare_names_are_left_alone(session):
    """Две перезаливки — ещё не артист: карточка с одним треком хуже никакой."""
    await _tracks(session, "random uploader", 2)
    report = await artist_resolve.resolve_unbound(session, lookup=lambda _n: None)
    assert report.tracks_bound == 0
    assert await session.scalar(select(Artist)) is None


async def test_unknown_to_deezer_still_gets_a_plain_card(session):
    await _tracks(session, "lilmorty", 3)
    report = await artist_resolve.resolve_unbound(session, lookup=lambda _n: None)
    artist = await session.scalar(select(Artist))
    assert artist.name == "lilmorty" and artist.photo_url is None
    assert report.created_plain == 1 and report.tracks_bound == 3

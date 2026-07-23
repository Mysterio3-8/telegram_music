import pytest

from app.db.models import Artist, Track
from app.services.genres import (
    genre_tracks,
    genre_tree,
    get_genre_by_slug,
    seed_genres,
    set_artist_genres,
    slugify,
)


def test_slugify_translit_and_symbols():
    assert slugify("Drift Phonk") == "drift-phonk"
    assert slugify("Русский рэп") == "russkiy-rep"
    assert slugify("R&B и соул") == "r-b-i-soul"
    assert slugify("  80-е  ") == "80-e"


@pytest.mark.asyncio
async def test_seed_is_idempotent(session):
    created, _ = await seed_genres(session)
    assert created > 250  # «все существующие» — сид объёмный
    created_again, existed = await seed_genres(session)
    assert created_again == 0
    assert existed == created


@pytest.mark.asyncio
async def test_tree_has_three_levels(session):
    await seed_genres(session)
    tree = await genre_tree(session)
    electronic = next(n for n in tree if n["name"] == "Электроника")
    phonk = next(c for c in electronic["children"] if c["name"] == "Phonk")
    assert any(g["name"] == "Drift Phonk" for g in phonk["children"])


@pytest.mark.asyncio
async def test_genre_tracks_include_subgenres(session):
    await seed_genres(session)
    artist = Artist(name="DVRST", normalized_name="dvrst")
    session.add(artist)
    await session.commit()
    drift = await get_genre_by_slug(session, "drift-phonk")
    await set_artist_genres(session, artist.id, [drift.name])
    session.add(Track(title="Close Eyes", artist="DVRST", duration=150))
    session.add(Track(title="Чужой трек", artist="Кто-то ещё", duration=150))
    await session.commit()

    # Прямой жанр
    tracks, total = await genre_tracks(session, drift, 1, 10)
    assert total == 1 and tracks[0].title == "Close Eyes"
    # Родитель (Phonk) и топ-уровень (Электроника) наследуют трек поджанра
    phonk = await get_genre_by_slug(session, "phonk")
    _, total_phonk = await genre_tracks(session, phonk, 1, 10)
    assert total_phonk == 1
    electronic = await get_genre_by_slug(session, "elektronika")
    _, total_top = await genre_tracks(session, electronic, 1, 10)
    assert total_top == 1


@pytest.mark.asyncio
async def test_set_artist_genres_creates_unknown_as_top_level(session):
    await seed_genres(session)
    artist = Artist(name="X", normalized_name="x")
    session.add(artist)
    await session.commit()
    linked = await set_artist_genres(session, artist.id, ["Trap", "Совсем новый жанр", "Trap"])
    assert linked == 2  # дубль в списке не привязывается дважды
    new_genre = await get_genre_by_slug(session, "sovsem-novyy-zhanr")
    assert new_genre is not None and new_genre.parent_id is None

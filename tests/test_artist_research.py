import json

import pytest
from sqlalchemy import select

from app.db.models import Artist, SoundcloudSource, YoutubeSource
from app.services.artist_research import (
    artists_without_source,
    attach_source_for_artist,
    save_researched,
)
from app.services.genres import artist_genre_names
from app.services.musicbrainz import ResearchedArtist, parse_artist

MB_DETAILS = {
    "id": "abc-123",
    "name": "Kizaru",
    "country": "RU",
    "genres": [
        {"name": "hip hop", "count": 5},
        {"name": "trap", "count": 3},
        {"name": "", "count": 1},
    ],
    "aliases": [{"name": "Кизару"}, {"name": "Kizaru"}],
    "relations": [
        {"url": {"resource": "https://www.instagram.com/kizaru"}},
        {"url": {"resource": "https://soundcloud.com/kizaru_hf"}},
        {"url": {"resource": "https://www.youtube.com/channel/UCx"}},
    ],
}


def test_parse_artist_extracts_everything():
    parsed = parse_artist(MB_DETAILS)
    assert parsed.name == "Kizaru" and parsed.mbid == "abc-123"
    assert parsed.country == "RU"
    assert parsed.genres == ["Hip Hop", "Trap"]  # по убыванию count, пустые отброшены
    assert parsed.aliases == ["Кизару"]  # само имя не алиас
    assert parsed.soundcloud_url == "https://soundcloud.com/kizaru_hf"
    assert parsed.youtube_url == "https://www.youtube.com/channel/UCx"


@pytest.mark.asyncio
async def test_save_researched_upsert_and_no_overwrite(session):
    researched = parse_artist(MB_DETAILS)
    artist, created = await save_researched(session, researched, photo_url="http://d/p.jpg")
    assert created
    assert artist.mbid == "abc-123" and artist.country == "RU"
    assert json.loads(artist.aliases) == ["Кизару"]
    assert sorted(await artist_genre_names(session, artist.id)) == ["Hip Hop", "Trap"]

    # Повтор: не дублирует и не перетирает заполненное
    again = ResearchedArtist(name="Kizaru", mbid="abc-123", country="US")
    same, created_again = await save_researched(session, again)
    assert not created_again and same.id == artist.id
    assert same.country == "RU"  # существующее значение сохранено


@pytest.mark.asyncio
async def test_save_researched_merges_with_owner_seeded_artist(session):
    """Артист владельца (без mbid) дополняется данными MusicBrainz по имени."""
    session.add(Artist(name="Aarne", normalized_name="aarne", soundcloud_url="https://soundcloud.com/aarne0"))
    await session.commit()
    researched = ResearchedArtist(
        name="Aarne", mbid="mb-aarne", country="RU",
        soundcloud_url="https://soundcloud.com/other",
    )
    artist, created = await save_researched(session, researched)
    assert not created
    assert artist.mbid == "mb-aarne"
    assert artist.soundcloud_url == "https://soundcloud.com/aarne0"  # ссылка владельца важнее


@pytest.mark.asyncio
async def test_attach_sources_soundcloud_only(session):
    """Массовый парсер — SoundCloud-only (решение владельца): YouTube-артист
    получает no_source, YouTube-источник не заводится."""
    sc_artist = Artist(name="A", normalized_name="a",
                       soundcloud_url="https://soundcloud.com/a", youtube_url="https://youtube.com/@a")
    yt_artist = Artist(name="B", normalized_name="b", youtube_url="https://www.youtube.com/channel/UCb")
    empty = Artist(name="C", normalized_name="c")
    session.add_all([sc_artist, yt_artist, empty])
    await session.commit()

    assert await attach_source_for_artist(session, sc_artist) == "soundcloud"
    assert await attach_source_for_artist(session, yt_artist) == "no_source"  # YouTube не источник
    assert await attach_source_for_artist(session, empty) == "no_source"

    sc = await session.scalar(select(SoundcloudSource))
    assert sc.url == "https://soundcloud.com/a" and sc.title == "A"
    # YouTube-источник не создаётся вовсе
    assert (await session.scalars(select(YoutubeSource))).first() is None

    remaining = await artists_without_source(session, 10)
    assert remaining == []


@pytest.mark.asyncio
async def test_disable_research_youtube_sources(session):
    """Чистка: research-YouTube отключается, канал владельца остаётся."""
    from app.services.artist_research import disable_research_youtube_sources

    yt_artist = Artist(
        name="B", normalized_name="b",
        youtube_url="https://www.youtube.com/channel/UCb", source_status="youtube",
    )
    session.add(yt_artist)
    session.add(YoutubeSource(url="https://www.youtube.com/channel/UCb", title="B", status="active"))
    session.add(YoutubeSource(url="https://www.youtube.com/@owner_channel", title="Owner", status="active"))
    await session.commit()

    disabled = await disable_research_youtube_sources(session)
    assert disabled == 1
    research_src = await session.scalar(
        select(YoutubeSource).where(YoutubeSource.url == "https://www.youtube.com/channel/UCb")
    )
    assert research_src.status == "disabled"
    owner_src = await session.scalar(
        select(YoutubeSource).where(YoutubeSource.url == "https://www.youtube.com/@owner_channel")
    )
    assert owner_src.status == "active"  # канал владельца не тронут
    await session.refresh(yt_artist)
    assert yt_artist.source_status == "no_source"

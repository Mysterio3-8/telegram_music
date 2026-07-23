"""Сохранение результатов исследователя (SPEC-КАТАЛОГ §3-4).

Upsert артиста по mbid → по нормализованному имени; пустые поля дополняются,
заполненные не перетираются (данные владельца важнее автоматики).
"""
import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Artist, YoutubeSource
from app.services.artist_entities import normalize_name
from app.services.genres import set_artist_genres
from app.services.musicbrainz import ResearchedArtist
from app.services.soundcloud_sources import add_source as add_soundcloud_source


async def save_researched(
    session: AsyncSession,
    researched: ResearchedArtist,
    *,
    photo_url: str | None = None,
    banner_url: str | None = None,
    deezer_id: int | None = None,
) -> tuple[Artist, bool]:
    """Возвращает (артист, создан_ли). Жанры привязываются всегда (идемпотентно)."""
    artist = await session.scalar(select(Artist).where(Artist.mbid == researched.mbid))
    created = False
    if artist is None:
        artist = await session.scalar(
            select(Artist).where(Artist.normalized_name == normalize_name(researched.name))
        )
    if artist is None:
        artist = Artist(
            name=researched.name.strip(),
            normalized_name=normalize_name(researched.name),
        )
        session.add(artist)
        created = True

    artist.mbid = artist.mbid or researched.mbid
    artist.country = artist.country or researched.country
    artist.soundcloud_url = artist.soundcloud_url or researched.soundcloud_url
    artist.youtube_url = artist.youtube_url or researched.youtube_url
    artist.photo_url = artist.photo_url or photo_url
    artist.banner_url = artist.banner_url or banner_url
    artist.deezer_id = artist.deezer_id or deezer_id
    if researched.aliases and not artist.aliases:
        artist.aliases = json.dumps(researched.aliases, ensure_ascii=False)
    await session.commit()

    if researched.genres:
        await set_artist_genres(session, artist.id, researched.genres)
    return artist, created


async def attach_source_for_artist(session: AsyncSession, artist: Artist) -> str:
    """Регистрирует источник закачки (§4): SoundCloud приоритетнее YouTube.
    Возвращает и пишет в artist.source_status: soundcloud | youtube | no_source."""
    if artist.soundcloud_url:
        await add_soundcloud_source(session, artist.soundcloud_url, title=artist.name)
        status = "soundcloud"
    elif artist.youtube_url:
        clean = artist.youtube_url.strip().rstrip("/")
        existing = await session.scalar(select(YoutubeSource).where(YoutubeSource.url == clean))
        if existing is None:
            session.add(YoutubeSource(url=clean, title=artist.name, status="active"))
        status = "youtube"
    else:
        status = "no_source"
    artist.source_status = status
    await session.commit()
    return status


async def artists_without_source(session: AsyncSession, limit: int) -> list[Artist]:
    rows = await session.scalars(
        select(Artist).where(Artist.source_status.is_(None)).order_by(Artist.id).limit(limit)
    )
    return list(rows.all())

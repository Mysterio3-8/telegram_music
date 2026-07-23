"""Карточка артиста для Mini App (SPEC-КАТАЛОГ §2): сущность + жанры +
топ треков по прослушиваниям + альбомы. Треки связаны по нормализованному имени.
"""
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Artist, Track, TrackEvent
from app.services.artist_entities import get_artist_by_name, normalize_name
from app.services.genres import artist_genre_names

TOP_TRACKS_LIMIT = 10


@dataclass
class AlbumSummary:
    name: str
    track_count: int
    cover_url: str | None = None


@dataclass
class ArtistCard:
    name: str
    photo_url: str | None = None
    banner_url: str | None = None
    description: str | None = None
    country: str | None = None
    genres: list[str] = field(default_factory=list)
    track_count: int = 0
    top_tracks: list[Track] = field(default_factory=list)
    albums: list[AlbumSummary] = field(default_factory=list)


def _artist_match(name: str):
    return func.lower(func.trim(Track.artist)) == normalize_name(name)


async def _top_tracks(session: AsyncSession, name: str) -> list[Track]:
    """По прослушиваниям; хвост без событий добивается свежими треками."""
    listened = await session.execute(
        select(Track, func.count(TrackEvent.id).label("listens"))
        .join(TrackEvent, (TrackEvent.track_id == Track.id) & (TrackEvent.event == "listen"))
        .where(_artist_match(name))
        .group_by(Track.id)
        .order_by(func.count(TrackEvent.id).desc())
        .limit(TOP_TRACKS_LIMIT)
    )
    tracks = [row[0] for row in listened.all()]
    if len(tracks) < TOP_TRACKS_LIMIT:
        seen = {t.id for t in tracks}
        fresh = await session.scalars(
            select(Track)
            .where(_artist_match(name))
            .order_by(Track.id.desc())
            .limit(TOP_TRACKS_LIMIT + len(seen))
        )
        for track in fresh:
            if track.id not in seen and len(tracks) < TOP_TRACKS_LIMIT:
                tracks.append(track)
    return tracks


async def _albums(session: AsyncSession, name: str) -> list[AlbumSummary]:
    rows = await session.execute(
        select(Track.album, func.count(), func.max(Track.cover_url))
        .where(_artist_match(name), Track.album.is_not(None), func.trim(Track.album) != "")
        .group_by(Track.album)
        .order_by(func.count().desc())
    )
    return [
        AlbumSummary(name=album, track_count=count, cover_url=cover)
        for album, count, cover in rows.all()
    ]


async def get_artist_card(session: AsyncSession, name: str) -> ArtistCard:
    """Карточка живёт даже без записи в artists — по одним трекам."""
    entity: Artist | None = await get_artist_by_name(session, name)
    track_count = (
        await session.scalar(select(func.count()).select_from(Track).where(_artist_match(name)))
    ) or 0
    card = ArtistCard(name=entity.name if entity else name.strip(), track_count=track_count)
    if entity is not None:
        card.photo_url = entity.photo_url
        card.banner_url = entity.banner_url
        card.description = entity.description
        card.country = entity.country
        card.genres = await artist_genre_names(session, entity.id)
    card.top_tracks = await _top_tracks(session, name)
    card.albums = await _albums(session, name)
    return card

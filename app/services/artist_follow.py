"""Подписка на артистов + похожие артисты (референс VK/Яндекс.Музыки).

Похожие — по общим жанрам, затем по стране (у кого нет жанров). Это дёшево и
не требует внешних сервисов: каталог уже размечен жанрами исследователем.
"""
from dataclasses import dataclass

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Artist, ArtistGenre, Track, UserArtist


async def follow_artist(session: AsyncSession, user_id: int, artist_id: int) -> bool:
    """Подписаться. True — подписка создана, False — уже была."""
    if await session.get(UserArtist, (user_id, artist_id)) is not None:
        return False
    session.add(UserArtist(user_id=user_id, artist_id=artist_id))
    await session.commit()
    return True


async def unfollow_artist(session: AsyncSession, user_id: int, artist_id: int) -> None:
    await session.execute(
        delete(UserArtist).where(
            UserArtist.user_id == user_id, UserArtist.artist_id == artist_id
        )
    )
    await session.commit()


async def is_following(session: AsyncSession, user_id: int, artist_id: int) -> bool:
    return await session.get(UserArtist, (user_id, artist_id)) is not None


@dataclass
class FollowedArtist:
    id: int
    name: str
    photo_url: str | None
    track_count: int


async def followed_artists(session: AsyncSession, user_id: int) -> list[FollowedArtist]:
    """«Мои артисты»: подписки пользователя с числом треков (через artist_id/имя)."""
    rows = await session.scalars(
        select(Artist)
        .join(UserArtist, UserArtist.artist_id == Artist.id)
        .where(UserArtist.user_id == user_id)
        .order_by(UserArtist.created_at.desc())
    )
    artists = list(rows.all())
    result: list[FollowedArtist] = []
    for artist in artists:
        count = (
            await session.scalar(
                select(func.count())
                .select_from(Track)
                .where(
                    (Track.artist_id == artist.id)
                    | (
                        Track.artist_id.is_(None)
                        & (func.lower(func.trim(Track.artist)) == artist.normalized_name)
                    )
                )
            )
        ) or 0
        result.append(
            FollowedArtist(
                id=artist.id, name=artist.name, photo_url=artist.photo_url, track_count=count
            )
        )
    return result


@dataclass
class SimilarArtist:
    name: str
    photo_url: str | None


async def similar_artists(
    session: AsyncSession, artist: Artist, limit: int = 10
) -> list[SimilarArtist]:
    """Похожие: сначала делящие жанр (по числу общих жанров), добор — земляки."""
    genre_ids = list(
        (
            await session.scalars(
                select(ArtistGenre.genre_id).where(ArtistGenre.artist_id == artist.id)
            )
        ).all()
    )
    picked: list[Artist] = []
    seen = {artist.id}
    if genre_ids:
        shared = func.count(ArtistGenre.genre_id).label("shared")
        rows = await session.execute(
            select(Artist, shared)
            .join(ArtistGenre, ArtistGenre.artist_id == Artist.id)
            .where(ArtistGenre.genre_id.in_(genre_ids), Artist.id != artist.id)
            .group_by(Artist.id)
            .order_by(shared.desc(), Artist.id)
            .limit(limit)
        )
        for row in rows.all():
            picked.append(row[0])
            seen.add(row[0].id)

    if len(picked) < limit and artist.country:
        rows = await session.scalars(
            select(Artist)
            .where(Artist.country == artist.country, Artist.id.notin_(seen))
            .order_by(Artist.id)
            .limit(limit - len(picked))
        )
        picked.extend(rows.all())

    return [SimilarArtist(name=a.name, photo_url=a.photo_url) for a in picked]

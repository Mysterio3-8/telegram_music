"""Артисты как сущности (P4): сид из списка владельца, фото, привязка к трекам по имени.

Треки связываются по lower(trim(tracks.artist)) — жёсткий artist_id появится
после ручной чистки имён.
"""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Artist


def normalize_name(name: str) -> str:
    return name.strip().lower()


async def upsert_artist(
    session: AsyncSession,
    name: str,
    *,
    soundcloud_url: str | None = None,
    photo_url: str | None = None,
    description: str | None = None,
) -> tuple[Artist, bool]:
    """Создаёт артиста или дополняет существующего (пустые поля). (артист, создан_ли)."""
    normalized = normalize_name(name)
    existing = await session.scalar(select(Artist).where(Artist.normalized_name == normalized))
    if existing is not None:
        changed = False
        if soundcloud_url and not existing.soundcloud_url:
            existing.soundcloud_url = soundcloud_url
            changed = True
        if photo_url and not existing.photo_url:
            existing.photo_url = photo_url
            changed = True
        if description and not existing.description:
            existing.description = description
            changed = True
        if changed:
            await session.commit()
        return existing, False

    artist = Artist(
        name=name.strip(),
        normalized_name=normalized,
        soundcloud_url=soundcloud_url,
        photo_url=photo_url,
        description=description,
    )
    session.add(artist)
    await session.commit()
    return artist, True


async def get_artist_by_name(session: AsyncSession, name: str) -> Artist | None:
    return await session.scalar(
        select(Artist).where(Artist.normalized_name == normalize_name(name))
    )


async def artists_photo_map(session: AsyncSession) -> dict[str, str]:
    """normalized_name → photo_url для обогащения списка исполнителей в Mini App."""
    rows = await session.execute(
        select(Artist.normalized_name, Artist.photo_url).where(Artist.photo_url.is_not(None))
    )
    return {name: url for name, url in rows.all()}


async def set_artist_photo(session: AsyncSession, artist_id: int, photo_url: str) -> None:
    artist = await session.get(Artist, artist_id)
    if artist is None:
        return
    artist.photo_url = photo_url
    await session.commit()


async def artists_without_photo(session: AsyncSession, limit: int = 50) -> list[Artist]:
    """Кандидаты на дозагрузку аватара (есть SoundCloud-ссылка, нет фото)."""
    rows = await session.scalars(
        select(Artist)
        .where(Artist.photo_url.is_(None), Artist.soundcloud_url.is_not(None))
        .order_by(Artist.id)
        .limit(limit)
    )
    return list(rows)


async def count_artists(session: AsyncSession) -> int:
    return (await session.scalar(select(func.count()).select_from(Artist))) or 0

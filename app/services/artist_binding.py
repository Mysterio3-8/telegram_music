"""Привязка треков к артистам-сущностям (SPEC-КАТАЛОГ §6).

Матч: lower(trim(tracks.artist)) ↔ artists.normalized_name + алиасы из
artists.aliases (JSON). Новые импорты зовут resolve_artist_id, бэкфилл старых —
bind_tracks (CLI). Несвязанные — unbound_report владельцу на чистку.
"""
import json
from dataclasses import dataclass

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Artist, Track
from app.services.artist_entities import normalize_name


async def resolve_artist_id(session: AsyncSession, artist_name: str) -> int | None:
    """Артист по точному нормализованному имени — для одиночного импорта."""
    if not artist_name or not artist_name.strip():
        return None
    return await session.scalar(
        select(Artist.id).where(Artist.normalized_name == normalize_name(artist_name))
    )


async def _name_to_id_map(session: AsyncSession) -> dict[str, int]:
    """normalized_name + алиасы → artist_id. Имя сильнее алиаса, ранний артист
    сильнее позднего (при коллизии алиасов побеждает меньший id — детерминизм)."""
    rows = await session.execute(
        select(Artist.id, Artist.normalized_name, Artist.aliases).order_by(Artist.id.desc())
    )
    mapping: dict[str, int] = {}
    alias_map: dict[str, int] = {}
    for artist_id, normalized, aliases_json in rows.all():
        mapping[normalized] = artist_id
        if aliases_json:
            try:
                for alias in json.loads(aliases_json):
                    alias_map[normalize_name(alias)] = artist_id
            except (ValueError, TypeError):
                continue
    return {**alias_map, **mapping}  # прямые имена перекрывают алиасы


async def bind_tracks(session: AsyncSession) -> int:
    """Бэкфилл artist_id для непривязанных треков. Возвращает число привязанных.
    Нормализация — в Python: SQLite lower() не понижает кириллицу (грабля из CLAUDE.md),
    поэтому группируем сырые написания и матчим update по точной строке."""
    mapping = await _name_to_id_map(session)
    rows = await session.execute(
        select(Track.artist).where(Track.artist_id.is_(None)).distinct()
    )
    bound = 0
    for (raw,) in rows.all():
        artist_id = mapping.get(normalize_name(raw or ""))
        if artist_id is None:
            continue
        result = await session.execute(
            update(Track)
            .where(Track.artist_id.is_(None), Track.artist == raw)
            .values(artist_id=artist_id)
        )
        bound += result.rowcount or 0
    await session.commit()
    return bound


@dataclass
class UnboundArtist:
    name: str
    track_count: int


async def unbound_report(session: AsyncSession, limit: int = 30) -> list[UnboundArtist]:
    """Имена без артиста-сущности, по убыванию числа треков — владельцу на чистку."""
    rows = await session.execute(
        select(func.max(func.trim(Track.artist)), func.count())
        .where(Track.artist_id.is_(None))
        .group_by(func.lower(func.trim(Track.artist)))
        .order_by(func.count().desc())
        .limit(limit)
    )
    return [UnboundArtist(name=name, track_count=count) for name, count in rows.all()]

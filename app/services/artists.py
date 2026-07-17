"""Исполнители общей базы с дедупликацией по нормализованному имени (ТЗ §13-14).

«Куратор = исполнитель»: раздел кураторов Mini App показывает этот же список.
Один человек под разными написаниями («Miyagi», « miyagi ») схлопывается
в одну строку; каноническое имя — самое частое написание не выбрать дёшево,
берём max() как детерминированный вариант.
"""
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Track


@dataclass
class ArtistSummary:
    name: str
    track_count: int


def _norm_expr():
    return func.lower(func.trim(Track.artist))


async def list_artists(session: AsyncSession) -> list[ArtistSummary]:
    rows = await session.execute(
        select(func.max(func.trim(Track.artist)), func.count())
        .where(Track.artist.is_not(None), func.trim(Track.artist) != "")
        .group_by(_norm_expr())
        .order_by(func.count().desc(), func.max(func.trim(Track.artist)))
    )
    return [ArtistSummary(name=name, track_count=count) for name, count in rows.all()]


async def artist_tracks(session: AsyncSession, name: str) -> list[Track]:
    rows = await session.scalars(
        select(Track).where(_norm_expr() == name.strip().lower()).order_by(Track.id.desc())
    )
    return list(rows.all())

"""Движок рекомендаций (доп. ТЗ): собирает «микс» под настроение/тип/язык.

- Язык выводится из текста (кириллица → русская, иначе → зарубежная).
- Настроение — по проставленному админом Track.mood; мягкий фильтр: применяется
  только если есть помеченные треки, иначе игнорируется (микс не должен пустеть).
- Тип: новые — по дате добавления; известные/неизвестные — по числу прослушиваний.
"""
import random
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Instrumental, Track, TrackEvent

MIX_LIMIT = 60
VALID_MOODS = {"happy", "sad", "energetic", "calm", "love"}


async def instrumental_mix(session: AsyncSession, limit: int = MIX_LIMIT) -> list[Instrumental]:
    """Микс «Инструментальная» — минусы из отдельной таблицы, в случайном порядке."""
    items = list((await session.scalars(select(Instrumental))).all())
    random.shuffle(items)
    return items[:limit]


def detect_language(text: str) -> str:
    for ch in text:
        low = ch.lower()
        if "а" <= low <= "я" or low == "ё":
            return "russian"
    return "foreign"


async def _play_counts(session: AsyncSession) -> dict[int, int]:
    rows = await session.execute(
        select(TrackEvent.track_id, func.count())
        .where(TrackEvent.event == "listen")
        .group_by(TrackEvent.track_id)
    )
    return {track_id: count for track_id, count in rows.all()}


async def build_mix(
    session: AsyncSession,
    mood: str | None = None,
    recognizability: str | None = None,
    language: str | None = None,
    limit: int = MIX_LIMIT,
) -> list[Track]:
    tracks = list((await session.scalars(select(Track))).all())
    if not tracks:
        return []

    if language in ("russian", "foreign"):
        filtered = [t for t in tracks if detect_language(f"{t.title} {t.artist}") == language]
        tracks = filtered or tracks  # не оставляем пустой микс

    if mood in VALID_MOODS:
        tagged = [t for t in tracks if t.mood == mood]
        if tagged:
            tracks = tagged

    if recognizability == "new":
        tracks.sort(key=lambda t: t.created_at or datetime.min, reverse=True)
    elif recognizability in ("known", "unknown"):
        counts = await _play_counts(session)
        tracks.sort(key=lambda t: counts.get(t.id, 0), reverse=(recognizability == "known"))
    else:
        random.shuffle(tracks)

    return tracks[:limit]

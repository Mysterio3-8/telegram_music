"""Альбомы, релизы и обложки для треков каталога — из самого источника (22.09).

Владелец: «сформировать альбомы, плейлисты, релизы». Замер прода 24.09: альбом
указан у 281 трека из 8547 (3%), обложки нет у 3718. Экран «Альбомы» в Mini App
собирается из `tracks.album` — отсюда почти пустая витрина.

Источник знает больше, чем мы сохранили: карточка трека SoundCloud отдаёт
`publisher_metadata.album_title`, дату релиза, жанр и обложку. У 21 сентября
быстрый путь уже пишет альбом при скачивании; этот проход дотягивает то же самое
для каталога, залитого раньше.

Правила:
- трогаем только ПУСТЫЕ поля — данные, поправленные админом, не перетираются;
- обложку апскейлим до t500x500 (artwork_url приходит «-large», это 100×100);
- `meta_checked_at` ставится КАЖДОМУ тронутому треку, даже если источник ничего
  не дал, — иначе ночной проход вечно перебирал бы одни и те же синглы.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Track

logger = logging.getLogger(__name__)

# Через сколько снова спрашивать источник о треке, где ничего не нашлось:
# лейблы дописывают метаданные к релизам и после выхода.
RETRY_AFTER = timedelta(days=30)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@dataclass
class EnrichReport:
    checked: int = 0
    albums: int = 0
    covers: int = 0
    failed: int = 0


async def due_tracks(session: AsyncSession, limit: int) -> list[Track]:
    """Треки SoundCloud, у которых чего-то не хватает и которых давно не сверяли.

    Свежие первыми: их чаще всего и открывают, пока они на слуху.
    """
    cutoff = _utcnow() - RETRY_AFTER
    stmt = (
        select(Track)
        .where(
            Track.source_url.like("%soundcloud.com/%"),
            or_(Track.album.is_(None), Track.album == "", Track.cover_url.is_(None), Track.cover_url == ""),
            or_(Track.meta_checked_at.is_(None), Track.meta_checked_at < cutoff),
        )
        .order_by(Track.id.desc())
        .limit(limit)
    )
    return list((await session.scalars(stmt)).all())


def fetch_source_meta(source_url: str) -> dict | None:
    """Карточка трека из API SoundCloud v2. None — источник не ответил."""
    from app.services.soundcloud_api import api_get

    data = api_get("/resolve", {"url": source_url})
    if not isinstance(data, dict) or data.get("kind") != "track":
        return None
    return data


def apply_meta(track: Track, data: dict) -> tuple[bool, bool]:
    """Дописывает пустые поля. Возвращает (альбом, обложка) — что добавилось."""
    from app.services.soundcloud import upscale_soundcloud_artwork
    from app.services.mojibake import repair

    publisher = data.get("publisher_metadata") or {}
    added_album = added_cover = False

    album = repair((publisher.get("album_title") or "").strip())
    if album and not (track.album or "").strip():
        track.album = album[:256]
        added_album = True

    artwork = data.get("artwork_url") or (data.get("user") or {}).get("avatar_url") or ""
    if artwork and not (track.cover_url or "").strip():
        track.cover_url = upscale_soundcloud_artwork(artwork)
        added_cover = True

    return added_album, added_cover


async def enrich_tracks(session: AsyncSession, limit: int = 100, fetch=fetch_source_meta) -> EnrichReport:
    import asyncio

    report = EnrichReport()
    for track in await due_tracks(session, limit):
        report.checked += 1
        # Отметка ДО похода в сеть: процесс на этом боксе убивали посреди работы,
        # и трек не должен снова оказываться первым в очереди.
        track.meta_checked_at = _utcnow()
        try:
            data = await asyncio.to_thread(fetch, track.source_url)
        except Exception:  # noqa: BLE001 — источник лёг: трек вернётся через RETRY_AFTER
            logger.warning("Метаданные track=%s не получены", track.id, exc_info=True)
            data = None
        if data is None:
            report.failed += 1
        else:
            album, cover = apply_meta(track, data)
            report.albums += album
            report.covers += cover
        await session.commit()
    return report

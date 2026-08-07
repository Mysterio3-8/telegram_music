"""Движок рекомендаций и Infinity Mix.

Infinity Mix собирается под вкус пользователя, а не случайной солянкой:
- профиль вкуса — веса артистов из прослушиваний (×3), библиотеки (×2), подписок (×4);
- состав ~60 треков: половина — любимые артисты, треть — соседи по жанру
  (другие артисты того же вайба), остаток — открытия из каталога;
- не больше 2 треков одного артиста подряд;
- уже показанное за последние 7 дней (mix_history) не повторяем;
- явно не-музыкальные названия (клипы/премьеры) отсекаются.

Новичку без истории — микс по свежести каталога (пустого экрана не будет).

Настройки экрана «Настроить» (mood/recognizability/language) остаются мягкими
фильтрами поверх собранного пула.
"""
import random
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    ArtistGenre,
    Instrumental,
    MixHistory,
    Track,
    TrackEvent,
    UserArtist,
    UserLibrary,
)
from app.services.title_quality import is_probably_junk

MIX_LIMIT = 60
VALID_MOODS = {"happy", "sad", "energetic", "calm", "love"}

HISTORY_DAYS = 7
TASTE_ARTIST_CAP = 40  # сколько топ-артистов вкуса берём в ядро
MAX_ARTIST_RUN = 2  # не больше стольких треков одного артиста подряд

WEIGHT_LISTEN = 3
WEIGHT_LIBRARY = 2
WEIGHT_FOLLOW = 4


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


# ---------- профиль вкуса ----------


async def _taste_artist_weights(session: AsyncSession, user_id: int) -> dict[int, float]:
    """Веса артистов по вовлечённости пользователя (artist_id → вес)."""
    weights: dict[int, float] = defaultdict(float)

    listens = await session.execute(
        select(Track.artist_id, func.count())
        .join(TrackEvent, TrackEvent.track_id == Track.id)
        .where(
            TrackEvent.user_id == user_id,
            TrackEvent.event == "listen",
            Track.artist_id.is_not(None),
        )
        .group_by(Track.artist_id)
    )
    for artist_id, count in listens.all():
        weights[artist_id] += WEIGHT_LISTEN * count

    library = await session.execute(
        select(Track.artist_id, func.count())
        .join(UserLibrary, UserLibrary.track_id == Track.id)
        .where(UserLibrary.user_id == user_id, Track.artist_id.is_not(None))
        .group_by(Track.artist_id)
    )
    for artist_id, count in library.all():
        weights[artist_id] += WEIGHT_LIBRARY * count

    follows = await session.scalars(
        select(UserArtist.artist_id).where(UserArtist.user_id == user_id)
    )
    for artist_id in follows.all():
        weights[artist_id] += WEIGHT_FOLLOW

    return weights


async def _genres_of(session: AsyncSession, artist_ids: list[int]) -> list[int]:
    if not artist_ids:
        return []
    rows = await session.scalars(
        select(ArtistGenre.genre_id).where(ArtistGenre.artist_id.in_(artist_ids)).distinct()
    )
    return list(rows.all())


# ---------- выборки-кандидаты (SQL с лимитом, не весь каталог) ----------


async def _by_artists(
    session: AsyncSession, artist_ids: list[int], exclude_ids: set[int], limit: int
) -> list[Track]:
    if not artist_ids:
        return []
    stmt = select(Track).where(
        Track.artist_id.in_(artist_ids), Track.moderation_status == "approved"
    )
    if exclude_ids:
        stmt = stmt.where(Track.id.not_in(exclude_ids))
    stmt = stmt.order_by(func.random()).limit(limit)
    return list((await session.scalars(stmt)).all())


async def _by_genres(
    session: AsyncSession,
    genre_ids: list[int],
    exclude_artist_ids: set[int],
    exclude_ids: set[int],
    limit: int,
) -> list[Track]:
    if not genre_ids:
        return []
    artists_in_genres = select(ArtistGenre.artist_id).where(ArtistGenre.genre_id.in_(genre_ids))
    stmt = select(Track).where(
        Track.artist_id.in_(artists_in_genres), Track.moderation_status == "approved"
    )
    if exclude_artist_ids:
        stmt = stmt.where(Track.artist_id.not_in(exclude_artist_ids))
    if exclude_ids:
        stmt = stmt.where(Track.id.not_in(exclude_ids))
    stmt = stmt.order_by(func.random()).limit(limit)
    return list((await session.scalars(stmt)).all())


async def _discovery(session: AsyncSession, exclude_ids: set[int], limit: int) -> list[Track]:
    stmt = select(Track).where(Track.moderation_status == "approved")
    if exclude_ids:
        stmt = stmt.where(Track.id.not_in(exclude_ids))
    stmt = stmt.order_by(func.random()).limit(limit)
    return list((await session.scalars(stmt)).all())


async def _fresh(session: AsyncSession, exclude_ids: set[int], limit: int) -> list[Track]:
    """Новичку без вкуса — свежие треки каталога вперемешку."""
    stmt = select(Track).where(Track.moderation_status == "approved")
    if exclude_ids:
        stmt = stmt.where(Track.id.not_in(exclude_ids))
    stmt = stmt.order_by(Track.created_at.desc()).limit(limit)
    return list((await session.scalars(stmt)).all())


# ---------- история показов ----------


async def _recently_shown(session: AsyncSession, user_id: int) -> set[int]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=HISTORY_DAYS)
    await session.execute(
        delete(MixHistory).where(MixHistory.user_id == user_id, MixHistory.created_at < cutoff)
    )
    rows = await session.scalars(select(MixHistory.track_id).where(MixHistory.user_id == user_id))
    return set(rows.all())


async def _record_shown(session: AsyncSession, user_id: int, track_ids: list[int]) -> None:
    session.add_all(MixHistory(user_id=user_id, track_id=tid) for tid in track_ids)
    await session.flush()


# ---------- сборка ----------


def _spread_artists(tracks: list[Track]) -> list[Track]:
    """Разложить, чтобы не шло больше MAX_ARTIST_RUN треков одного артиста подряд."""
    result: list[Track] = []
    pending = list(tracks)
    while pending:
        placed = False
        for i, track in enumerate(pending):
            recent = result[-MAX_ARTIST_RUN:]
            if len(recent) == MAX_ARTIST_RUN and all(r.artist == track.artist for r in recent):
                continue
            result.append(pending.pop(i))
            placed = True
            break
        if not placed:  # остались только треки того же артиста — кладём как есть
            result.append(pending.pop(0))
    return result


def _dedupe(tracks: list[Track]) -> list[Track]:
    seen: set[int] = set()
    out: list[Track] = []
    for track in tracks:
        if track.id in seen:
            continue
        seen.add(track.id)
        out.append(track)
    return out


def _apply_soft_filters(
    tracks: list[Track],
    mood: str | None,
    language: str | None,
) -> list[Track]:
    if language in ("russian", "foreign"):
        filtered = [t for t in tracks if detect_language(f"{t.title} {t.artist}") == language]
        tracks = filtered or tracks
    if mood in VALID_MOODS:
        tagged = [t for t in tracks if t.mood == mood]
        if tagged:
            tracks = tagged
    return tracks


async def build_mix(
    session: AsyncSession,
    user_id: int | None = None,
    mood: str | None = None,
    recognizability: str | None = None,
    language: str | None = None,
    limit: int = MIX_LIMIT,
) -> list[Track]:
    recent_ids = await _recently_shown(session, user_id) if user_id else set()
    weights = await _taste_artist_weights(session, user_id) if user_id else {}
    taste_ids = [aid for aid, _ in sorted(weights.items(), key=lambda kv: -kv[1])[:TASTE_ARTIST_CAP]]

    if taste_ids:
        genre_ids = await _genres_of(session, taste_ids)
        core = await _by_artists(session, taste_ids, recent_ids, limit)
        seen = recent_ids | {t.id for t in core}
        neighbors = await _by_genres(session, genre_ids, set(taste_ids), seen, limit)
        seen |= {t.id for t in neighbors}
        discovery = await _discovery(session, seen, limit)
    else:
        core, neighbors = [], []
        discovery = await _fresh(session, recent_ids, limit * 3)

    core = [t for t in core if not is_probably_junk(t.title)]
    neighbors = [t for t in neighbors if not is_probably_junk(t.title)]
    discovery = [t for t in discovery if not is_probably_junk(t.title)]

    random.shuffle(core)
    random.shuffle(neighbors)
    random.shuffle(discovery)

    pool = core[: int(limit * 0.5)] + neighbors[: int(limit * 0.3)] + discovery
    pool = _dedupe(pool)

    if not pool:  # каталог мал/всё показано — берём хоть что-то, игнорируя историю
        pool = _dedupe([t for t in await _discovery(session, set(), limit) if not is_probably_junk(t.title)])

    pool = _apply_soft_filters(pool, mood, language)

    if recognizability == "new":
        pool.sort(key=lambda t: t.created_at or datetime.min, reverse=True)
        result = pool[:limit]
    elif recognizability in ("known", "unknown"):
        counts = await _play_counts(session)
        pool.sort(key=lambda t: counts.get(t.id, 0), reverse=(recognizability == "known"))
        result = pool[:limit]
    else:
        result = _spread_artists(pool)[:limit]

    if user_id and result:
        await _record_shown(session, user_id, [t.id for t in result])
    return result

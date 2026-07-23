"""Жанры каталога (SPEC-КАТАЛОГ §1): сид, дерево, треки жанра.

Трек наследует жанры артиста: genres → artist_genres → artists →
tracks по lower(trim(tracks.artist)) == artists.normalized_name.
"""
import re

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.genres_seed import GENRE_TREE
from app.db.models import Artist, ArtistGenre, Genre, Track

_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def slugify(name: str) -> str:
    lowered = name.strip().lower()
    transliterated = "".join(_TRANSLIT.get(ch, ch) for ch in lowered)
    return re.sub(r"[^a-z0-9]+", "-", transliterated).strip("-")


async def _get_or_create(
    session: AsyncSession, name: str, parent_id: int | None
) -> tuple[Genre, bool]:
    slug = slugify(name)
    existing = await session.scalar(select(Genre).where(Genre.slug == slug))
    if existing is not None:
        return existing, False
    genre = Genre(name=name, slug=slug, parent_id=parent_id)
    session.add(genre)
    await session.flush()
    return genre, True


async def seed_genres(session: AsyncSession) -> tuple[int, int]:
    """Идемпотентный сид из GENRE_TREE. Возвращает (создано, уже_было)."""
    created = existed = 0
    for top_name, children in GENRE_TREE.items():
        top, is_new = await _get_or_create(session, top_name, None)
        created += is_new
        existed += not is_new
        for child in children:
            if isinstance(child, dict):  # третий уровень: {"Phonk": ["Drift Phonk", …]}
                for mid_name, grandchildren in child.items():
                    mid, is_new = await _get_or_create(session, mid_name, top.id)
                    created += is_new
                    existed += not is_new
                    for grand_name in grandchildren:
                        _, is_new = await _get_or_create(session, grand_name, mid.id)
                        created += is_new
                        existed += not is_new
            else:
                _, is_new = await _get_or_create(session, child, top.id)
                created += is_new
                existed += not is_new
    await session.commit()
    return created, existed


async def genre_tree(session: AsyncSession) -> list[dict]:
    """Всё дерево жанров одним запросом — для GET /genres и чипов Mini App."""
    rows = await session.scalars(select(Genre).order_by(Genre.id))
    genres = list(rows.all())
    by_id: dict[int, dict] = {
        g.id: {"id": g.id, "name": g.name, "slug": g.slug, "children": []} for g in genres
    }
    roots: list[dict] = []
    for genre in genres:
        node = by_id[genre.id]
        if genre.parent_id is None:
            roots.append(node)
        else:
            by_id[genre.parent_id]["children"].append(node)
    return roots


async def get_genre_by_slug(session: AsyncSession, slug: str) -> Genre | None:
    return await session.scalar(select(Genre).where(Genre.slug == slug))


async def _descendant_ids(session: AsyncSession, genre_id: int) -> list[int]:
    """Жанр + все потомки (иерархия ≤3 уровней — два прохода достаточно)."""
    ids = [genre_id]
    frontier = [genre_id]
    for _ in range(2):
        rows = await session.scalars(select(Genre.id).where(Genre.parent_id.in_(frontier)))
        frontier = list(rows.all())
        if not frontier:
            break
        ids.extend(frontier)
    return ids


async def genre_tracks(
    session: AsyncSession, genre: Genre, page: int, page_size: int
) -> tuple[list[Track], int]:
    """Треки жанра (включая поджанры) через артистов. Свежие сверху."""
    genre_ids = await _descendant_ids(session, genre.id)
    artist_names = (
        select(Artist.normalized_name)
        .join(ArtistGenre, ArtistGenre.artist_id == Artist.id)
        .where(ArtistGenre.genre_id.in_(genre_ids))
    )
    condition = func.lower(func.trim(Track.artist)).in_(artist_names)
    total = (
        await session.scalar(select(func.count()).select_from(Track).where(condition))
    ) or 0
    rows = await session.scalars(
        select(Track)
        .where(condition)
        .order_by(Track.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(rows.all()), total


async def set_artist_genres(
    session: AsyncSession, artist_id: int, genre_names: list[str]
) -> int:
    """Привязка жанров артисту (исследователь MusicBrainz). Неизвестный жанр
    создаётся топ-уровнем — каталог должен вмещать «все существующие» (§1).
    Возвращает число привязанных жанров."""
    linked = 0
    existing_rows = await session.scalars(
        select(ArtistGenre.genre_id).where(ArtistGenre.artist_id == artist_id)
    )
    already = set(existing_rows.all())
    for name in genre_names:
        clean = name.strip()
        if not clean:
            continue
        genre, _ = await _get_or_create(session, clean, None)
        if genre.id in already:
            continue
        session.add(ArtistGenre(artist_id=artist_id, genre_id=genre.id))
        already.add(genre.id)
        linked += 1
    await session.commit()
    return linked


async def artist_genre_names(session: AsyncSession, artist_id: int) -> list[str]:
    rows = await session.scalars(
        select(Genre.name)
        .join(ArtistGenre, ArtistGenre.genre_id == Genre.id)
        .where(ArtistGenre.artist_id == artist_id)
        .order_by(Genre.name)
    )
    return list(rows.all())

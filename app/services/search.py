from dataclasses import dataclass, field

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import Artist, Instrumental, Playlist, Track


def _track_filter(query: str):
    """Поиск по автору, названию и любому их сочетанию — вплоть до одной буквы.

    Основной путь — нормализованный search_index (нижний регистр + транслит
    посчитаны в Python): только он находит кириллицу на SQLite, где lower()/ILIKE
    работают лишь для ASCII, из-за чего запрос «ки» не находил «Кизару».
    ILIKE по title/artist оставлен для треков без индекса (бэкфилл идёт фоном)."""
    from app.services.search_index import normalize_search_query
    from app.services.track_lookup.ranking import to_latin

    pattern = f"%{query.strip()}%"
    normalized = normalize_search_query(query)
    conditions = [
        Track.search_index.ilike(f"%{normalized}%"),
        Track.title.ilike(pattern),
        Track.artist.ilike(pattern),
    ]
    # Запрос кириллицей должен находить трек, записанный латиницей:
    # «кизару» → «kizaru». Обратное направление уже покрыто индексом.
    latin = to_latin(normalized)
    if latin != normalized:
        conditions.append(Track.search_index.ilike(f"%{latin}%"))
    # Немодерированные (pending/rejected) не показываем в поиске (блок D)
    return and_(or_(*conditions), Track.moderation_status == "approved")


async def find_track_by_metadata(
    session: AsyncSession, artist: str, title: str
) -> Track | None:
    """Трек, уже залитый под тем же «исполнитель — название». None — такого нет.

    Живой поиск спрашивает это ДО скачивания: если трек уже минтили, он уходит
    пользователю мгновенно по file_id, и качать его повторно незачем. Сравниваем
    по search_index — единственному полю, где регистр и транслит уже приведены
    (SQLite lower() кириллицу не понижает).
    """
    from app.services.search_index import build_search_index

    index = build_search_index(artist, title)
    if not index:
        return None
    stmt = select(Track).where(
        Track.search_index == index, Track.moderation_status == "approved"
    )
    return (await session.scalars(stmt.limit(1))).first()


async def find_track_by_source_url(session: AsyncSession, url: str) -> Track | None:
    """Трек, уже залитый с этой самой страницы источника. None — такого нет.

    Точнее сверки по «исполнитель — название»: в поисковой выдаче у трека один
    заголовок, а в скачанном файле другой (источник дописывает «Official Audio»,
    «prod. …»), из-за чего уже залитый трек не опознавался и качался заново —
    лишние секунды ожидания, а на DRM-копии ещё и ложное «трек под защитой».
    """
    if not url:
        return None
    stmt = select(Track).where(
        Track.source_url == url, Track.moderation_status == "approved"
    )
    return (await session.scalars(stmt.limit(1))).first()


async def search_tracks(
    session: AsyncSession, query: str, page: int, page_size: int | None = None
) -> tuple[list[Track], int]:
    """Поиск по общей базе. Возвращает (страница результатов, всего найдено).

    page_size переопределяется только Mini App (пачки до 100); бот всегда на дефолте.
    """
    size = page_size or settings.page_size
    where = _track_filter(query)
    total = await session.scalar(select(func.count()).select_from(Track).where(where)) or 0
    stmt = (
        select(Track)
        .where(where)
        .order_by(Track.artist, Track.title)
        .offset((page - 1) * size)
        .limit(size)
    )
    return list((await session.scalars(stmt)).all()), total


def _instrumental_filter(query: str):
    pattern = f"%{query.strip()}%"
    return or_(Instrumental.title.ilike(pattern), Instrumental.artist.ilike(pattern))


async def search_instrumentals(
    session: AsyncSession, query: str, page: int, page_size: int | None = None
) -> tuple[list[Instrumental], int]:
    size = page_size or settings.page_size
    where = _instrumental_filter(query)
    total = await session.scalar(select(func.count()).select_from(Instrumental).where(where)) or 0
    stmt = (
        select(Instrumental)
        .where(where)
        .order_by(Instrumental.artist, Instrumental.title)
        .offset((page - 1) * size)
        .limit(size)
    )
    return list((await session.scalars(stmt)).all()), total


async def get_instrumental(session: AsyncSession, instrumental_id: int) -> Instrumental | None:
    return await session.get(Instrumental, instrumental_id)


@dataclass
class SearchArtist:
    name: str
    photo_url: str | None = None


@dataclass
class SearchAlbum:
    name: str
    track_count: int
    cover_url: str | None = None


@dataclass
class SectionedResults:
    artists: list[SearchArtist] = field(default_factory=list)
    albums: list[SearchAlbum] = field(default_factory=list)
    playlists: list[Playlist] = field(default_factory=list)
    tracks: list[Track] = field(default_factory=list)


SECTION_LIMIT = 8


async def _search_artists(session: AsyncSession, query: str) -> list[SearchArtist]:
    """Артисты-сущности по имени; добор — исполнители из треков (ещё без сущности)."""
    pattern = f"%{query.strip()}%"
    entities = await session.scalars(
        select(Artist).where(Artist.name.ilike(pattern)).order_by(Artist.id).limit(SECTION_LIMIT)
    )
    result = [SearchArtist(name=a.name, photo_url=a.photo_url) for a in entities.all()]
    seen = {r.name.lower() for r in result}
    if len(result) < SECTION_LIMIT:
        rows = await session.execute(
            select(func.max(func.trim(Track.artist)))
            .where(Track.artist.ilike(pattern))
            .group_by(func.lower(func.trim(Track.artist)))
            .limit(SECTION_LIMIT * 2)
        )
        for (name,) in rows.all():
            if name and name.lower() not in seen and len(result) < SECTION_LIMIT:
                result.append(SearchArtist(name=name))
                seen.add(name.lower())
    return result


async def _search_albums(session: AsyncSession, query: str) -> list[SearchAlbum]:
    """Альбомы, где название альбома ИЛИ артист подходят под запрос (референс:
    в выдаче по имени артиста видны его альбомы)."""
    pattern = f"%{query.strip()}%"
    rows = await session.execute(
        select(Track.album, func.count(), func.max(Track.cover_url))
        .where(
            Track.album.is_not(None),
            func.trim(Track.album) != "",
            or_(Track.album.ilike(pattern), Track.artist.ilike(pattern)),
        )
        .group_by(Track.album)
        .order_by(func.count().desc())
        .limit(SECTION_LIMIT)
    )
    return [
        SearchAlbum(name=album, track_count=count, cover_url=cover)
        for album, count, cover in rows.all()
    ]


async def _search_playlists(session: AsyncSession, query: str) -> list[Playlist]:
    pattern = f"%{query.strip()}%"
    rows = await session.scalars(
        select(Playlist).where(Playlist.title.ilike(pattern)).order_by(Playlist.id).limit(SECTION_LIMIT)
    )
    return list(rows.all())


async def search_all(session: AsyncSession, query: str) -> SectionedResults:
    """Секционная выдача поиска (референс): Артисты / Альбомы / Плейлисты / Треки."""
    if not query.strip():
        return SectionedResults()
    tracks, _ = await search_tracks(session, query, 1, SECTION_LIMIT)
    return SectionedResults(
        artists=await _search_artists(session, query),
        albums=await _search_albums(session, query),
        playlists=await _search_playlists(session, query),
        tracks=tracks,
    )

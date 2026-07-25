from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.api.deps import get_current_user
from app.api.schemas import (
    ArtistAlbumOut,
    ArtistCardOut,
    FollowedArtistOut,
    GenreOut,
    InstrumentalOut,
    Page,
    PlaylistSummaryOut,
    SearchAlbumOut,
    SearchArtistOut,
    SearchSectionsOut,
    SimilarArtistOut,
    TrackOut,
    track_out,
)
from app.api.security import build_instrumental_audio_url
from app.config import settings
from app.db.models import Instrumental, User
from app.services.artist_card import get_artist_card
from app.services.artist_entities import get_artist_by_name
from app.services.artist_follow import (
    follow_artist,
    followed_artists,
    is_following,
    similar_artists,
    unfollow_artist,
)
from app.services.genres import genre_tracks, genre_tree, get_genre_by_slug
from app.services.library import get_track
from app.services.playlists import count_playlist_tracks
from app.services.search import (
    get_instrumental,
    search_all,
    search_instrumentals,
    search_tracks,
)


def instrumental_track_out(item: Instrumental) -> TrackOut:
    """Минус в формате трека Mini App: отрицательный id (не пересекается с треками),
    аудио — через /instrumentals/{id}/audio с собственной подписью."""
    return TrackOut(
        id=-item.id,
        title=item.title,
        artist=item.artist,
        duration=item.duration,
        audio_url=build_instrumental_audio_url(item.id),
    )

router = APIRouter(tags=["catalog"], dependencies=[Depends(get_current_user)])

MINIAPP_MAX_PAGE_SIZE = 100


@router.get("/tracks", response_model=Page[TrackOut])
async def list_tracks(
    q: str = "",
    page: int = Query(1, ge=1),
    page_size: int = Query(None, ge=1, le=MINIAPP_MAX_PAGE_SIZE),
    session: AsyncSession = Depends(get_db),
) -> Page[TrackOut]:
    tracks, total = await search_tracks(session, q, page, page_size)
    return Page(
        items=[track_out(t) for t in tracks],
        total=total,
        page=page,
        page_size=page_size or settings.page_size,
    )


@router.get("/search", response_model=Page[TrackOut])
async def search(
    q: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(None, ge=1, le=MINIAPP_MAX_PAGE_SIZE),
    session: AsyncSession = Depends(get_db),
) -> Page[TrackOut]:
    tracks, total = await search_tracks(session, q, page, page_size)
    return Page(
        items=[track_out(t) for t in tracks],
        total=total,
        page=page,
        page_size=page_size or settings.page_size,
    )


@router.get("/search/all", response_model=SearchSectionsOut)
async def search_sections(
    q: str, session: AsyncSession = Depends(get_db)
) -> SearchSectionsOut:
    """Секционная выдача поиска (референс): Артисты / Альбомы / Плейлисты / Треки."""
    results = await search_all(session, q)
    playlists = [
        PlaylistSummaryOut(
            id=p.id, title=p.title, track_count=await count_playlist_tracks(session, p.id)
        )
        for p in results.playlists
    ]
    return SearchSectionsOut(
        artists=[SearchArtistOut(name=a.name, photo_url=a.photo_url) for a in results.artists],
        albums=[
            SearchAlbumOut(name=a.name, track_count=a.track_count, cover_url=a.cover_url)
            for a in results.albums
        ],
        playlists=playlists,
        tracks=[track_out(t) for t in results.tracks],
    )


@router.get("/track/{track_id}", response_model=TrackOut)
async def get_track_by_id(
    track_id: int, session: AsyncSession = Depends(get_db)
) -> TrackOut:
    """Свежий трек со свежей подписанной аудио-ссылкой. Отрицательный id — минус
    (конвенция Mini App): фронт освежает протухшие ссылки единым эндпоинтом."""
    if track_id < 0:
        instrumental = await get_instrumental(session, -track_id)
        if instrumental is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Минус не найден")
        return instrumental_track_out(instrumental)
    track = await get_track(session, track_id)
    if track is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Трек не найден")
    return track_out(track)


@router.get("/instrumentals", response_model=Page[TrackOut])
async def list_instrumentals(
    q: str = "",
    page: int = Query(1, ge=1),
    page_size: int = Query(None, ge=1, le=MINIAPP_MAX_PAGE_SIZE),
    session: AsyncSession = Depends(get_db),
) -> Page[TrackOut]:
    """Поиск минусов для Mini App (вкладка «Минусы» в поиске)."""
    items, total = await search_instrumentals(session, q, page, page_size)
    return Page(
        items=[instrumental_track_out(i) for i in items],
        total=total,
        page=page,
        page_size=page_size or settings.page_size,
    )


@router.get("/artist-card", response_model=ArtistCardOut)
async def artist_card(
    name: str = Query(..., min_length=1),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ArtistCardOut:
    """Карточка артиста (SPEC-КАТАЛОГ §2 + референсы): фото, баннер, жанры,
    последний релиз, топ, синглы, альбомы, похожие, статус подписки."""
    card = await get_artist_card(session, name)
    entity = await get_artist_by_name(session, name)
    following = bool(entity) and await is_following(session, user.id, entity.id)
    similar = await similar_artists(session, entity) if entity else []
    return ArtistCardOut(
        name=card.name,
        photo_url=card.photo_url,
        banner_url=card.banner_url,
        description=card.description,
        country=card.country,
        genres=card.genres,
        track_count=card.track_count,
        following=following,
        artist_id=entity.id if entity else None,
        latest_release=track_out(card.latest_release) if card.latest_release else None,
        top_tracks=[track_out(t) for t in card.top_tracks],
        singles=[track_out(t) for t in card.singles],
        albums=[
            ArtistAlbumOut(name=a.name, track_count=a.track_count, cover_url=a.cover_url)
            for a in card.albums
        ],
        similar=[SimilarArtistOut(name=s.name, photo_url=s.photo_url) for s in similar],
    )


@router.post("/artists/{artist_id}/follow", status_code=status.HTTP_204_NO_CONTENT)
async def follow(
    artist_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    await follow_artist(session, user.id, artist_id)


@router.delete("/artists/{artist_id}/follow", status_code=status.HTTP_204_NO_CONTENT)
async def unfollow(
    artist_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    await unfollow_artist(session, user.id, artist_id)


@router.get("/my/artists", response_model=list[FollowedArtistOut])
async def my_artists(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[FollowedArtistOut]:
    """«Мои артисты» — подписки пользователя (референс: раздел библиотеки)."""
    return [
        FollowedArtistOut(id=a.id, name=a.name, photo_url=a.photo_url, track_count=a.track_count)
        for a in await followed_artists(session, user.id)
    ]


@router.get("/genres", response_model=list[GenreOut])
async def list_genres(session: AsyncSession = Depends(get_db)) -> list[GenreOut]:
    """Дерево жанров каталога (SPEC-КАТАЛОГ §1) — чипы поиска Mini App."""
    return [GenreOut(**node) for node in await genre_tree(session)]


@router.get("/genres/{slug}/tracks", response_model=Page[TrackOut])
async def tracks_by_genre(
    slug: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(None, ge=1, le=MINIAPP_MAX_PAGE_SIZE),
    session: AsyncSession = Depends(get_db),
) -> Page[TrackOut]:
    """Треки жанра и его поджанров — через жанры артистов."""
    genre = await get_genre_by_slug(session, slug)
    if genre is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Жанр не найден")
    size = page_size or settings.page_size
    tracks, total = await genre_tracks(session, genre, page, size)
    return Page(items=[track_out(t) for t in tracks], total=total, page=page, page_size=size)


@router.get("/instrumental/{instrumental_id}", response_model=InstrumentalOut)
async def get_instrumental_by_id(
    instrumental_id: int, session: AsyncSession = Depends(get_db)
) -> InstrumentalOut:
    instrumental = await get_instrumental(session, instrumental_id)
    if instrumental is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Минус не найден")
    return instrumental

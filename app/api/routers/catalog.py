from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.api.schemas import InstrumentalOut, Page, TrackOut, track_out
from app.api.security import build_instrumental_audio_url
from app.config import settings
from app.db.models import Instrumental
from app.services.library import get_track
from app.services.search import get_instrumental, search_instrumentals, search_tracks


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


@router.get("/track/{track_id}", response_model=TrackOut)
async def get_track_by_id(
    track_id: int, session: AsyncSession = Depends(get_db)
) -> TrackOut:
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


@router.get("/instrumental/{instrumental_id}", response_model=InstrumentalOut)
async def get_instrumental_by_id(
    instrumental_id: int, session: AsyncSession = Depends(get_db)
) -> InstrumentalOut:
    instrumental = await get_instrumental(session, instrumental_id)
    if instrumental is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Минус не найден")
    return instrumental

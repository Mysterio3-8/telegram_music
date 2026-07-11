from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.api.schemas import InstrumentalOut, Page, TrackOut
from app.config import settings
from app.services.library import get_track
from app.services.search import get_instrumental, search_instrumentals, search_tracks

router = APIRouter(tags=["catalog"], dependencies=[Depends(get_current_user)])


@router.get("/tracks", response_model=Page[TrackOut])
async def list_tracks(
    q: str = "",
    page: int = Query(1, ge=1),
    session: AsyncSession = Depends(get_db),
) -> Page[TrackOut]:
    tracks, total = await search_tracks(session, q, page)
    return Page(items=tracks, total=total, page=page, page_size=settings.page_size)


@router.get("/search", response_model=Page[TrackOut])
async def search(
    q: str,
    page: int = Query(1, ge=1),
    session: AsyncSession = Depends(get_db),
) -> Page[TrackOut]:
    tracks, total = await search_tracks(session, q, page)
    return Page(items=tracks, total=total, page=page, page_size=settings.page_size)


@router.get("/track/{track_id}", response_model=TrackOut)
async def get_track_by_id(
    track_id: int, session: AsyncSession = Depends(get_db)
) -> TrackOut:
    track = await get_track(session, track_id)
    if track is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Трек не найден")
    return track


@router.get("/instrumentals", response_model=Page[InstrumentalOut])
async def list_instrumentals(
    q: str = "",
    page: int = Query(1, ge=1),
    session: AsyncSession = Depends(get_db),
) -> Page[InstrumentalOut]:
    items, total = await search_instrumentals(session, q, page)
    return Page(items=items, total=total, page=page, page_size=settings.page_size)


@router.get("/instrumental/{instrumental_id}", response_model=InstrumentalOut)
async def get_instrumental_by_id(
    instrumental_id: int, session: AsyncSession = Depends(get_db)
) -> InstrumentalOut:
    instrumental = await get_instrumental(session, instrumental_id)
    if instrumental is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Минус не найден")
    return instrumental

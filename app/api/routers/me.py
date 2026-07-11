from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.api.schemas import (
    Page,
    PlaylistCreateIn,
    PlaylistOut,
    PremiumStatusOut,
    TrackOut,
)
from app.config import settings
from app.db.models import User
from app.importers.base import ImportItem
from app.services.audio import duration_from_bytes
from app.services.catalog_import import import_user_track
from app.services.library import get_library_page, get_random_track
from app.services.playlists import create_playlist
from app.services.premium import can_create_playlist, can_upload, is_premium_active
from app.services.uploads import detect_format
from app.services.users import count_library_tracks
from app.storage import get_storage

router = APIRouter(tags=["me"])


@router.get("/library", response_model=Page[TrackOut])
async def my_library(
    page: int = Query(1, ge=1),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Page[TrackOut]:
    total = await count_library_tracks(session, user.id)
    tracks = await get_library_page(session, user.id, page)
    return Page(items=tracks, total=total, page=page, page_size=settings.page_size)


@router.get("/random", response_model=TrackOut)
async def random_track(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> TrackOut:
    track = await get_random_track(session, user.id)
    if track is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Библиотека пуста")
    return track


@router.post("/playlist", response_model=PlaylistOut, status_code=status.HTTP_201_CREATED)
async def create_my_playlist(
    payload: PlaylistCreateIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> PlaylistOut:
    title = payload.title.strip()
    if not title:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Пустое название")
    if not await can_create_playlist(session, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Лимит плейлистов бесплатного тарифа")
    return await create_playlist(session, user.id, title)


@router.post("/upload", response_model=TrackOut, status_code=status.HTTP_201_CREATED)
async def upload_track(
    title: str = Form(...),
    artist: str = Form(...),
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> TrackOut:
    if not await can_upload(session, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Лимит загрузок бесплатного тарифа")

    file_format = detect_format(file.filename, file.content_type)
    if file_format is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Неподдерживаемый формат")

    data = await file.read()
    if len(data) > settings.max_file_size_mb * 1024 * 1024:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Файл больше {settings.max_file_size_mb} МБ")

    duration = duration_from_bytes(data, suffix=f".{file_format}")
    if duration <= 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Не удалось прочитать аудио")

    item = ImportItem(
        title=title.strip(),
        artist=artist.strip(),
        duration=duration,
        data=data,
        file_format=file_format,
    )
    return await import_user_track(session, get_storage(), user.id, item)


@router.get("/premium/status", response_model=PremiumStatusOut)
async def premium_status(user: User = Depends(get_current_user)) -> PremiumStatusOut:
    return PremiumStatusOut(
        active=is_premium_active(user),
        until=user.premium_until if is_premium_active(user) else None,
        price_stars=settings.premium_price_stars,
        price_rub=settings.premium_price_rub,
    )

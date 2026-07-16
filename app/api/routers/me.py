from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.api.schemas import (
    AchievementOut,
    AlbumOut,
    LyricsIn,
    LyricsOut,
    Page,
    PlaylistCreateIn,
    PlaylistOut,
    PlaylistSummaryOut,
    PremiumStatusOut,
    ProfileOut,
    RankOut,
    ReferralOut,
    TrackOut,
    UserStatsOut,
    track_out,
)
from app.config import settings
from app.db.models import Track, User
from app.importers.base import ImportItem
from app.services.audio import duration_from_bytes
from app.services.catalog_import import import_user_track
from app.services.gamification import (
    build_achievements,
    collect_user_stats,
    referral_link,
    referral_rank,
)
from app.services.library import (
    add_to_library,
    get_library_page,
    get_random_track,
    get_track,
    remove_from_library,
)
from app.services.lyrics import get_or_fetch_lyrics, save_lyrics
from app.services.playlists import (
    count_playlist_tracks,
    create_playlist,
    get_all_playlists,
    get_playlist,
    get_playlist_tracks_page,
)
from app.services.recommendations import build_mix
from app.services.premium import can_create_playlist, can_upload, is_premium_active
from app.services.stats import record_event
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
    return Page(
        items=[track_out(t) for t in tracks], total=total, page=page, page_size=settings.page_size
    )


@router.get("/library/ids", response_model=list[int])
async def my_library_ids(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[int]:
    """Все id треков библиотеки — Mini App отмечает «в библиотеке» в любых списках."""
    from sqlalchemy import select

    from app.db.models import UserLibrary

    rows = await session.scalars(
        select(UserLibrary.track_id).where(UserLibrary.user_id == user.id)
    )
    return list(rows.all())


@router.post("/library/{track_id}", status_code=status.HTTP_204_NO_CONTENT)
async def add_track_to_library(
    track_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    if await get_track(session, track_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Трек не найден")
    await add_to_library(session, user.id, track_id)


@router.delete("/library/{track_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_track_from_library(
    track_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    await remove_from_library(session, user.id, track_id)


@router.get("/random", response_model=TrackOut)
async def random_track(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> TrackOut:
    track = await get_random_track(session, user.id)
    if track is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Библиотека пуста")
    return track_out(track)


@router.get("/mix", response_model=list[TrackOut])
async def personalized_mix(
    mood: str | None = Query(None),
    recognizability: str | None = Query(None),
    language: str | None = Query(None),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[TrackOut]:
    """Микс под настроение/тип/язык (доп. ТЗ, настройки рекомендаций)."""
    tracks = await build_mix(session, mood=mood, recognizability=recognizability, language=language)
    return [track_out(t) for t in tracks]


@router.get("/playlists", response_model=list[PlaylistSummaryOut])
async def my_playlists(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[PlaylistSummaryOut]:
    playlists = await get_all_playlists(session, user.id)
    return [
        PlaylistSummaryOut(
            id=p.id, title=p.title, track_count=await count_playlist_tracks(session, p.id)
        )
        for p in playlists
    ]


@router.get("/playlists/{playlist_id}/tracks", response_model=list[TrackOut])
async def playlist_tracks(
    playlist_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[TrackOut]:
    playlist = await get_playlist(session, playlist_id)
    if playlist is None or playlist.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Плейлист не найден")
    tracks: list = []
    page = 1
    while True:
        batch = await get_playlist_tracks_page(session, playlist_id, page)
        tracks += batch
        if len(batch) < settings.page_size:
            break
        page += 1
    return [track_out(t) for t in tracks]


@router.get("/albums", response_model=list[AlbumOut])
async def albums(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[AlbumOut]:
    rows = await session.execute(
        select(Track.album, func.count())
        .where(Track.album.is_not(None), Track.album != "")
        .group_by(Track.album)
        .order_by(func.count().desc())
    )
    return [AlbumOut(name=name, track_count=count) for name, count in rows.all()]


@router.get("/albums/tracks", response_model=list[TrackOut])
async def album_tracks(
    name: str = Query(..., min_length=1),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[TrackOut]:
    rows = await session.scalars(select(Track).where(Track.album == name))
    return [track_out(t) for t in rows.all()]


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


def _premium_status_out(user: User) -> PremiumStatusOut:
    discount = user.premium_discount_pct or 0
    base = settings.premium_price_rub
    effective = base * (100 - discount) // 100 if discount else base
    return PremiumStatusOut(
        active=is_premium_active(user),
        until=user.premium_until if is_premium_active(user) else None,
        price_stars=settings.premium_price_stars,
        price_rub=base,
        price_rub_effective=effective,
        discount_pct=discount,
    )


@router.get("/premium/status", response_model=PremiumStatusOut)
async def premium_status(user: User = Depends(get_current_user)) -> PremiumStatusOut:
    return _premium_status_out(user)


@router.post("/tracks/{track_id}/listen", status_code=status.HTTP_204_NO_CONTENT)
async def record_listen(
    track_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    """Mini App отмечает старт воспроизведения — сырьё для достижений/статистики."""
    if await get_track(session, track_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Трек не найден")
    await record_event(session, user.id, track_id, "listen")


@router.get("/tracks/{track_id}/lyrics", response_model=LyricsOut)
async def track_lyrics(
    track_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> LyricsOut:
    track = await get_track(session, track_id)
    if track is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Трек не найден")
    result = await get_or_fetch_lyrics(session, track)
    return LyricsOut(text=result.text, source=result.source, found=result.found)


@router.post(
    "/tracks/{track_id}/lyrics", response_model=LyricsOut, status_code=status.HTTP_201_CREATED
)
async def submit_lyrics(
    track_id: int,
    payload: LyricsIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> LyricsOut:
    if await get_track(session, track_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Трек не найден")
    text = payload.text.strip()
    if not text:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Пустой текст")
    row = await save_lyrics(session, track_id, text, source="user")
    return LyricsOut(text=row.text, source=row.source, found=True)


@router.get("/profile", response_model=ProfileOut)
async def profile(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ProfileOut:
    stats = await collect_user_stats(session, user)
    achievements = build_achievements(stats)
    progress = referral_rank(stats.invited)

    def rank_out(rank) -> RankOut | None:
        return RankOut(key=rank.key, title=rank.title, emoji=rank.emoji) if rank else None

    return ProfileOut(
        premium=_premium_status_out(user),
        referral=ReferralOut(
            link=referral_link(user.telegram_id, settings.bot_username),
            invited=stats.invited,
            rank=rank_out(progress.current),
            next_rank=rank_out(progress.next),
            to_next=progress.to_next,
        ),
        stats=UserStatsOut(
            listens=stats.listens,
            listen_hours=stats.listen_hours,
            streak_days=stats.streak_days,
            favorites=stats.favorites,
            playlists=stats.playlists,
        ),
        achievements_unlocked=sum(1 for a in achievements if a.unlocked),
        achievements_total=len(achievements),
        achievements=[
            AchievementOut(
                code=a.code,
                emoji=a.emoji,
                title=a.title,
                category=a.category,
                unlocked=a.unlocked,
                progress=a.progress,
                target=a.target,
            )
            for a in achievements
        ],
    )

import asyncio

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_premium
from app.api.schemas import (
    AchievementOut,
    AlbumOut,
    ArtistOut,
    LeaderRowOut,
    MilestoneOut,
    LyricsIn,
    LyricsOut,
    Page,
    PlaylistCreateIn,
    PlaylistOut,
    PlaylistSummaryOut,
    PremiumStatusOut,
    ProfileOut,
    ProfileTopOut,
    RankOut,
    AutorenewIn,
    LanguageIn,
    ReferralOut,
    SearchFetchIn,
    SearchLogIn,
    TrackOut,
    TransferIn,
    TransferStartOut,
    UserStatsOut,
    track_out,
)
from app.api.security import build_instrumental_audio_url
from app.config import settings
from app.db.models import Playlist, Track, User
from app.i18n import LANGUAGES, is_translated
from app.importers.base import ImportItem
from app.services.audio import duration_from_path
from app.services.catalog_import import import_user_track
from app.services.gamification import (
    REFERRAL_MILESTONES,
    build_achievements,
    collect_user_stats,
    count_referrals,
    grant_achievement_rewards,
    grant_referral_milestones,
    next_referral_reward,
    referral_leaderboard,
    referral_link,
    referral_rank,
    TRIAL_DAYS,
    start_trial,
    top_artists,
    top_tracks,
    with_premium_stats,
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
    add_track_to_playlist,
    count_tracks_by_playlist,
    create_playlist,
    get_all_playlists,
    get_playlist,
    get_playlist_tracks_all,
)
from app.services.artists import artist_tracks, list_artists
from app.services.recommendations import build_mix, instrumental_mix
from app.services.playlist_transfer.parsers import (
    TransferSourceError,
    fetch_playlist,
    parse_text_list,
)
from app.services.premium import can_create_playlist, can_upload, is_premium_active
from app.services.search_log import log_search_query, popular_queries
from app.services.stats import record_event
from app.services.telegram_send import send_audio_by_file_id
from app.services.uploads import detect_format
from app.services.users import count_library_tracks, set_user_language, user_language
from app.storage import get_storage

router = APIRouter(tags=["me"])

UPLOAD_MAX_TITLE = 256  # как MAX_TITLE_LENGTH мастера загрузки в боте
UPLOAD_SLOTS = 2
_upload_slots = asyncio.Semaphore(UPLOAD_SLOTS)


@router.get("/library", response_model=Page[TrackOut])
async def my_library(
    page: int = Query(1, ge=1),
    page_size: int = Query(None, ge=1, le=100),
    user: User = Depends(require_premium),
    session: AsyncSession = Depends(get_db),
) -> Page[TrackOut]:
    total = await count_library_tracks(session, user.id)
    tracks = await get_library_page(session, user.id, page, page_size)
    return Page(
        items=[track_out(t) for t in tracks],
        total=total,
        page=page,
        page_size=page_size or settings.page_size,
    )


@router.get("/library/ids", response_model=list[int])
async def my_library_ids(
    user: User = Depends(require_premium),
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
    user: User = Depends(require_premium),
    session: AsyncSession = Depends(get_db),
) -> None:
    if await get_track(session, track_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Трек не найден")
    await add_to_library(session, user.id, track_id)


@router.delete("/library/{track_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_track_from_library(
    track_id: int,
    user: User = Depends(require_premium),
    session: AsyncSession = Depends(get_db),
) -> None:
    await remove_from_library(session, user.id, track_id)


@router.get("/random", response_model=TrackOut)
async def random_track(
    user: User = Depends(require_premium),
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
    user: User = Depends(require_premium),
    session: AsyncSession = Depends(get_db),
) -> list[TrackOut]:
    """Микс под настроение/тип/язык (доп. ТЗ, настройки рекомендаций)."""
    if language == "instrumental":
        # Минусы — отдельная таблица; отрицательный id не пересекается с треками,
        # аудио идёт через /instrumentals/{id}/audio с собственной подписью
        items = await instrumental_mix(session)
        return [
            TrackOut(
                id=-item.id,
                title=item.title,
                artist=item.artist,
                duration=item.duration,
                audio_url=build_instrumental_audio_url(item.id),
            )
            for item in items
        ]
    tracks = await build_mix(
        session,
        user_id=user.id,
        mood=mood,
        recognizability=recognizability,
        language=language,
    )
    return [track_out(t) for t in tracks]


@router.post("/search/fetch", status_code=status.HTTP_202_ACCEPTED)
async def fetch_from_web(
    payload: SearchFetchIn,
    user: User = Depends(require_premium),
) -> dict:
    """Поисковый парсер (скрытый): нет в базе — ищем в открытых источниках,
    трек падает в библиотеку. Возвращаем сразу, работа — в Celery.

    quiet=True: запрос пришёл из Mini App, там человек и заберёт результат.
    Копию трека в чат бота владелец просил не слать — он её не запрашивал."""
    query = payload.query.strip()
    if not query:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Пустой запрос")
    try:
        from app.tasks.queue_client import enqueue

        enqueue(
            "search.fetch",
            query=query,
            telegram_id=user.telegram_id,
            chat_id=user.telegram_id,
            quiet=True,
        )
    except Exception as exc:  # noqa: BLE001 — брокер недоступен
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Поиск в сети недоступен") from exc
    return {"queued": True}


@router.post("/premium/autorenew", status_code=status.HTTP_204_NO_CONTENT)
async def set_autorenew(
    payload: AutorenewIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    """Включить/выключить автопродление Premium (блок E: требование оферты —
    пользователь может отключить в любой момент)."""
    db_user = await session.get(User, user.id)
    db_user.autorenew = payload.enabled
    await session.commit()


@router.get("/languages")
async def available_languages(user: User = Depends(get_current_user)) -> dict:
    """Список языков для переключателя + текущий выбор. Переведённые языки
    помечены: у остальных пока показывается английский."""
    return {
        "current": user_language(user),
        "items": [
            {
                "code": item.code,
                "title": item.title,
                "flag": item.flag,
                "translated": is_translated(item.code),
            }
            for item in LANGUAGES
        ],
    }


@router.post("/language", status_code=status.HTTP_204_NO_CONTENT)
async def choose_language(
    payload: LanguageIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    """Выбор языка общий с ботом: пишем в ту же users.ui_language."""
    db_user = await session.get(User, user.id)
    await set_user_language(session, db_user, payload.code)


@router.get("/playlists", response_model=list[PlaylistSummaryOut])
async def my_playlists(
    user: User = Depends(require_premium),
    session: AsyncSession = Depends(get_db),
) -> list[PlaylistSummaryOut]:
    playlists = await get_all_playlists(session, user.id)
    counts = await count_tracks_by_playlist(session, [p.id for p in playlists])
    return [
        PlaylistSummaryOut(id=p.id, title=p.title, track_count=counts.get(p.id, 0))
        for p in playlists
    ]


@router.get("/playlists/{playlist_id}/tracks", response_model=list[TrackOut])
async def playlist_tracks(
    playlist_id: int,
    user: User = Depends(require_premium),
    session: AsyncSession = Depends(get_db),
) -> list[TrackOut]:
    playlist = await get_playlist(session, playlist_id)
    if playlist is None or playlist.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Плейлист не найден")
    return [track_out(t) for t in await get_playlist_tracks_all(session, playlist_id)]


@router.get("/curators", response_model=list[PlaylistSummaryOut])
async def curated_playlists(
    user: User = Depends(require_premium),
    session: AsyncSession = Depends(get_db),
) -> list[PlaylistSummaryOut]:
    """Кураторские подборки — публичные плейлисты админов (ADMIN_IDS)."""
    if not settings.admin_id_set:
        return []
    admin_user_ids = list(
        (await session.scalars(select(User.id).where(User.telegram_id.in_(settings.admin_id_set)))).all()
    )
    if not admin_user_ids:
        return []
    playlists = (
        await session.scalars(
            select(Playlist)
            .where(Playlist.user_id.in_(admin_user_ids))
            .order_by(Playlist.created_at.desc())
        )
    ).all()
    counts = await count_tracks_by_playlist(session, [p.id for p in playlists])
    # пустые подборки не показываем
    return [
        PlaylistSummaryOut(id=p.id, title=p.title, track_count=counts[p.id])
        for p in playlists
        if counts.get(p.id)
    ]


@router.get("/curators/{playlist_id}/tracks", response_model=list[TrackOut])
async def curated_playlist_tracks(
    playlist_id: int,
    user: User = Depends(require_premium),
    session: AsyncSession = Depends(get_db),
) -> list[TrackOut]:
    playlist = await get_playlist(session, playlist_id)
    if playlist is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Подборка не найдена")
    owner = await session.get(User, playlist.user_id)
    if owner is None or owner.telegram_id not in settings.admin_id_set:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Подборка не найдена")
    return [track_out(t) for t in await get_playlist_tracks_all(session, playlist_id)]


@router.get("/artists", response_model=list[ArtistOut])
async def artists(
    response: Response,
    limit: int | None = Query(None, ge=1, le=5000),
    user: User = Depends(require_premium),
    session: AsyncSession = Depends(get_db),
) -> list[ArtistOut]:
    """Исполнители с дедупликацией по нормализованному имени (ТЗ §13).

    limit: онбордингу нужны 24 имени, а он тянул весь список — 58 КБ на проде
    (замер 14.09) на каждое первое открытие. Кэш вебвью на 5 минут: список
    меняется только с пополнением каталога."""
    response.headers["Cache-Control"] = "private, max-age=300"
    return [
        ArtistOut(name=a.name, track_count=a.track_count)
        for a in await list_artists(session, limit=limit)
    ]


@router.get("/artists/tracks", response_model=list[TrackOut])
async def tracks_by_artist(
    name: str = Query(..., min_length=1),
    user: User = Depends(require_premium),
    session: AsyncSession = Depends(get_db),
) -> list[TrackOut]:
    return [track_out(t) for t in await artist_tracks(session, name)]


@router.post("/search/log", status_code=status.HTTP_204_NO_CONTENT)
async def log_search(
    payload: SearchLogIn,
    user: User = Depends(require_premium),
    session: AsyncSession = Depends(get_db),
) -> None:
    """Mini App фиксирует «закоммиченный» запрос — сырьё для популярных (ТЗ §11)."""
    await log_search_query(session, user.id, payload.query)


@router.get("/search/popular", response_model=list[str])
async def popular_search_queries(
    user: User = Depends(require_premium),
    session: AsyncSession = Depends(get_db),
) -> list[str]:
    return await popular_queries(session)


@router.post("/transfer", response_model=TransferStartOut)
async def start_transfer(
    payload: TransferIn,
    user: User = Depends(require_premium),
) -> TransferStartOut:
    """Перенос плейлиста из другого сервиса (экран «Перенос из других сервисов»).
    Разбор источника — здесь (быстро), сам перенос — в Celery с отчётом в чат."""
    source = payload.source.strip()
    if not source:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Пустой источник")
    try:
        items = (
            await fetch_playlist(source) if source.startswith("http") else parse_text_list(source)
        )
    except TransferSourceError as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error))
    except Exception:  # noqa: BLE001 — чужой сервис недоступен/поменял формат
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Сервис не отдал список треков")

    if not items:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Не нашёл треков. Формат строки: Артист — Название"
        )
    if not settings.effective_celery_broker:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Перенос временно недоступен")

    from starlette.concurrency import run_in_threadpool

    from app.services.playlist_transfer.locks import (
        TRANSFER_MAX_ITEMS,
        acquire_transfer_lock,
        release_transfer_lock,
    )
    from app.tasks.queue_client import enqueue

    skipped = max(0, len(items) - TRANSFER_MAX_ITEMS)
    items = items[:TRANSFER_MAX_ITEMS]
    if not await run_in_threadpool(acquire_transfer_lock, user.telegram_id):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Предыдущий перенос ещё идёт — дождитесь отчёта в чате бота",
        )
    try:
        enqueue(
            "transfer.playlist",
            [{"artist": i.artist, "title": i.title} for i in items],
            user.telegram_id,
        )
    except Exception as exc:  # noqa: BLE001 — брокер лёг: замок не должен висеть сутки
        await run_in_threadpool(release_transfer_lock, user.telegram_id)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Перенос временно недоступен") from exc
    return TransferStartOut(
        queued=len(items),
        preview=[f"{i.artist} — {i.title}" for i in items[:5]],
        skipped=skipped,
    )


@router.post("/tracks/{track_id}/send", status_code=status.HTTP_204_NO_CONTENT)
async def send_track_to_chat(
    track_id: int,
    user: User = Depends(require_premium),
    session: AsyncSession = Depends(get_db),
) -> None:
    """«Скачать» в Mini App: бот присылает аудиофайл в чат пользователя (ТЗ §9)."""
    track = await get_track(session, track_id)
    if track is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Трек не найден")
    if not track.tg_file_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "Файл ещё обрабатывается — попробуйте позже")
    sent = await send_audio_by_file_id(
        user.telegram_id, track.tg_file_id, title=track.title, performer=track.artist
    )
    if not sent:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Не удалось отправить файл")
    await record_event(session, user.id, track_id, "download")


@router.get("/albums", response_model=list[AlbumOut])
async def albums(
    user: User = Depends(require_premium),
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
    user: User = Depends(require_premium),
    session: AsyncSession = Depends(get_db),
) -> list[TrackOut]:
    rows = await session.scalars(select(Track).where(Track.album == name))
    return [track_out(t) for t in rows.all()]


@router.post("/playlist", response_model=PlaylistOut, status_code=status.HTTP_201_CREATED)
async def create_my_playlist(
    payload: PlaylistCreateIn,
    user: User = Depends(require_premium),
    session: AsyncSession = Depends(get_db),
) -> PlaylistOut:
    title = payload.title.strip()
    if not title:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Пустое название")
    if not await can_create_playlist(session, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Лимит плейлистов бесплатного тарифа")
    return await create_playlist(session, user.id, title)


@router.post("/playlists/{playlist_id}/tracks/{track_id}", status_code=status.HTTP_204_NO_CONTENT)
async def add_to_playlist(
    playlist_id: int,
    track_id: int,
    user: User = Depends(require_premium),
    session: AsyncSession = Depends(get_db),
) -> None:
    """Добавить трек в плейлист (референс: шит «Добавить в плейлист»)."""
    playlist = await get_playlist(session, playlist_id)
    if playlist is None or playlist.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Плейлист не найден")
    # Внешние ключи в SQLite выключены: без проверки в плейлист ложилась строка на
    # несуществующий трек — счётчик показывал на трек больше, чем открывалось.
    if await get_track(session, track_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Трек не найден")
    await add_track_to_playlist(session, playlist_id, track_id)


@router.post("/upload", response_model=TrackOut, status_code=status.HTTP_201_CREATED)
async def upload_track(
    title: str = Form(...),
    artist: str = Form(...),
    file: UploadFile = File(...),
    user: User = Depends(require_premium),
    session: AsyncSession = Depends(get_db),
) -> TrackOut:
    # Те же границы, что у мастера загрузки в боте (handlers/upload.py). Пробелы
    # вместо названия раньше доходили до mutagen и роняли запрос в 500.
    title, artist = title.strip(), artist.strip()
    if not title or not artist or len(title) > UPLOAD_MAX_TITLE or len(artist) > UPLOAD_MAX_TITLE:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Название и исполнитель обязательны, до {UPLOAD_MAX_TITLE} символов",
        )
    if not await can_upload(session, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Лимит загрузок бесплатного тарифа")

    file_format = detect_format(file.filename, file.content_type)
    if file_format is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Неподдерживаемый формат")

    # Байты файла до 50 МБ всё ещё поднимаются в память один раз (хранилище берёт
    # bytes), а fpcalc занимает поток, поэтому одновременных загрузок не больше
    # UPLOAD_SLOTS: десять разом — это полгигабайта на боксе с 961 МБ. Лишнему —
    # честный отказ, а не OOM всем.
    if _upload_slots.locked():
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Сейчас идёт много загрузок — попробуйте через минуту",
            headers={"Retry-After": "60"},
        )
    async with _upload_slots:
        return await _receive_upload(session, user, file, file_format, title, artist)


async def _receive_upload(
    session: AsyncSession, user: User, file: UploadFile, file_format: str, title: str, artist: str
) -> TrackOut:

    import tempfile
    from pathlib import Path

    from starlette.concurrency import run_in_threadpool

    from app.services.fingerprint import compute_fingerprint

    # 🔴 Цикл 8, 15.09. Раньше файл копился в bytearray и копировался в bytes —
    # две копии до 50 МБ разом, а длительность (mutagen), отпечаток (fpcalc через
    # subprocess.run) и запись в хранилище шли синхронно прямо в event loop: пока
    # одна загрузка считала отпечаток, Mini App стоял у всех. Теперь поток пишется
    # во временный файл с остановкой на потолке, тяжёлое — в пуле потоков, а байты
    # поднимаются в память один раз, только для хранилища.
    limit = settings.max_file_size_mb * 1024 * 1024
    with tempfile.NamedTemporaryFile(suffix=f".{file_format}", delete=False) as tmp:
        tmp_path = Path(tmp.name)
        size = 0
        try:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > limit:
                    raise HTTPException(
                        status.HTTP_400_BAD_REQUEST, f"Файл больше {settings.max_file_size_mb} МБ"
                    )
                tmp.write(chunk)
        except BaseException:
            tmp.close()
            tmp_path.unlink(missing_ok=True)
            raise
    try:
        duration = await run_in_threadpool(duration_from_path, tmp_path)
        if duration <= 0:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Не удалось прочитать аудио")
        fingerprint = await run_in_threadpool(compute_fingerprint, str(tmp_path))
        data = await run_in_threadpool(tmp_path.read_bytes)
    finally:
        tmp_path.unlink(missing_ok=True)

    item = ImportItem(
        title=title.strip(),
        artist=artist.strip(),
        duration=duration,
        data=data,
        file_format=file_format,
    )
    return await import_user_track(session, get_storage(), user.id, item, fingerprint=fingerprint)


def _premium_status_out(user: User) -> PremiumStatusOut:
    discount = user.premium_discount_pct or 0
    base = settings.premium_price_rub
    effective = base * (100 - discount) // 100 if discount else base
    active = is_premium_active(user)
    return PremiumStatusOut(
        active=active,
        until=user.premium_until if active else None,
        price_stars=settings.premium_price_stars,
        price_rub=base,
        price_rub_effective=effective,
        discount_pct=discount,
        trial_available=not user.trial_used and not active,
        trial_days=TRIAL_DAYS,
    )


@router.get("/premium/status", response_model=PremiumStatusOut)
async def premium_status(user: User = Depends(get_current_user)) -> PremiumStatusOut:
    return _premium_status_out(user)


@router.post("/tracks/{track_id}/listen", status_code=status.HTTP_204_NO_CONTENT)
async def record_listen(
    track_id: int,
    user: User = Depends(require_premium),
    session: AsyncSession = Depends(get_db),
) -> None:
    """Mini App отмечает старт воспроизведения — сырьё для достижений/статистики."""
    if await get_track(session, track_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Трек не найден")
    await record_event(session, user.id, track_id, "listen")


@router.get("/tracks/{track_id}/lyrics", response_model=LyricsOut)
async def track_lyrics(
    track_id: int,
    user: User = Depends(require_premium),
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
    user: User = Depends(require_premium),
    session: AsyncSession = Depends(get_db),
) -> LyricsOut:
    # Текст общий для всех слушателей трека, а правка перезаписывает его целиком.
    # Интерфейс пускал к редактору только Premium, сервер — любого: бесплатный
    # аккаунт одним запросом затирал текст у всех (замер: 201).
    if not is_premium_active(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Добавление текста — с Premium")
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
    # Открытие профиля — момент, когда начисляем заработанные дни Premium.
    # Реферальные вехи пересчитываем здесь же: «живые» приглашённые (антинакрутка,
    # блок E) становятся активными со временем, и награда доначисляется на их фоне.
    # Профиль грузится при КАЖДОМ входе в приложение. Раньше статистика
    # считалась дважды, а приглашённые — трижды (~25 запросов); теперь один проход.
    invited = await count_referrals(session, user.telegram_id)
    await grant_referral_milestones(session, user, invited=invited)
    stats = await collect_user_stats(session, user, invited=invited)
    fresh = await grant_achievement_rewards(session, user, stats=stats)
    if fresh:
        stats = with_premium_stats(stats, user)
    achievements = build_achievements(stats)
    progress = referral_rank(stats.invited)
    to_next_reward, next_reward_days = next_referral_reward(stats.invited)

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
            to_next_reward=to_next_reward,
            next_reward_days=next_reward_days,
            milestones=[
                MilestoneOut(friends=friends, days=days)
                for friends, days in REFERRAL_MILESTONES
            ],
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
                reward_days=a.reward_days,
            )
            for a in achievements
        ],
        rewarded_days=sum(a.reward_days for a in fresh),
        trial_available=not user.trial_used and not is_premium_active(user),
    )


@router.post("/premium/trial", response_model=PremiumStatusOut)
async def start_premium_trial(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> PremiumStatusOut:
    """Пробный Premium в один тап — главный шаг к покупке: сначала дают попробовать."""
    if not await start_trial(session, user):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Пробный период уже был использован"
        )
    return _premium_status_out(user)


@router.get("/profile/top", response_model=ProfileTopOut)
async def profile_top(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ProfileTopOut:
    """Топ исполнителей и треков пользователя — блоки профиля по скринам VK."""
    artists = await top_artists(session, user.id)
    tracks = await top_tracks(session, user.id)
    return ProfileTopOut(
        artists=[ArtistOut(name=a.name, track_count=a.listens) for a in artists],
        tracks=[track_out(t) for t in tracks],
    )


@router.get("/referral/top", response_model=list[LeaderRowOut])
async def referral_top(
    session: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[LeaderRowOut]:
    rows = await referral_leaderboard(session)
    return [LeaderRowOut(name=r.name, invited=r.invited) for r in rows]

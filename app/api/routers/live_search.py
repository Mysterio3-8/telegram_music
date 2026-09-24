"""Живой поиск для Mini App: выдача прямо из источников и мгновенное
воспроизведение потоком, пока трек качается в фоне.

Два эндпоинта живут по разным правилам доступа, и это не оплошность:
`/search/live` — обычный JWT, `/stream/{ref}` подписан сам (тег <audio> не умеет
слать Authorization-заголовок — та же причина, что и у /tracks/{id}/audio).
"""
import logging
import time
from dataclasses import asdict

import aiohttp
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.api.deps import get_db, require_premium
from app.db.models import User
from app.services.candidate_ref import decode_ref, encode_ref
from app.services.search import find_tracks_by_metadata_bulk
from app.services.search_cache import search_with_cache
from app.services.shelves import SHELVES, build_personal_mix, build_shelf, get_shelf
from app.services.stream_url import resolve_stream_url
from app.services.track_lookup.metadata import candidate_metadata
from app.services.track_lookup.ranking import Candidate

logger = logging.getLogger(__name__)

router = APIRouter(tags=["live-search"])

_CHUNK = 64 * 1024

# Прямая ссылка источника по ref. Каждая перемотка — это новый Range-запрос, и
# раньше на каждый вызывался yt-dlp (секунды единственного ядра): десяток
# перемоток одного трека грузил сервер сильнее поиска. Ссылка источника живёт
# дольше десяти минут, при отказе источника запись выбрасывается.
_STREAM_URL_TTL = 600.0
_STREAM_URLS_MAX = 500
_stream_urls: dict[str, tuple[float, str]] = {}


async def _cached_stream_url(ref: str, candidate: Candidate) -> str | None:
    now = time.monotonic()
    hit = _stream_urls.get(ref)
    if hit is not None and hit[0] > now:
        return hit[1]
    url = await run_in_threadpool(resolve_stream_url, candidate)
    if url:
        if len(_stream_urls) >= _STREAM_URLS_MAX:
            for key in [k for k, (until, _) in _stream_urls.items() if until <= now]:
                _stream_urls.pop(key, None)
            if len(_stream_urls) >= _STREAM_URLS_MAX:
                _stream_urls.clear()
        _stream_urls[ref] = (now + _STREAM_URL_TTL, url)
    return url


class LiveTrackOut(BaseModel):
    """Кандидат живого поиска. `track_id` заполнен, если трек уже есть в базе —
    тогда Mini App играет его по обычной подписанной ссылке, минуя поток."""

    ref: str
    title: str
    artist: str
    duration: int
    source: str
    cover_url: str | None = None
    track_id: int | None = None
    # Заполнен только у треков каталога: подписанная ссылка на наши байты.
    # У живого кандидата аудио идёт через /stream/{ref}, ссылку строит клиент.
    audio_url: str | None = None


class LiveSearchOut(BaseModel):
    items: list[LiveTrackOut]


async def _to_outs(session: AsyncSession, candidates: list[Candidate]) -> list[LiveTrackOut]:
    metadata = [candidate_metadata(candidate) for candidate in candidates]
    existing = await find_tracks_by_metadata_bulk(session, metadata)
    return [
        LiveTrackOut(
            ref=encode_ref(candidate),
            title=title,
            artist=artist,
            duration=candidate.duration,
            source=candidate.source,
            cover_url=candidate.cover_url,
            track_id=track.id if track else None,
        )
        for candidate, (artist, title), track in zip(candidates, metadata, existing)
    ]


@router.get("/search/live", response_model=LiveSearchOut, dependencies=[Depends(require_premium)])
async def live_search(
    q: str = Query(..., min_length=1),
    session: AsyncSession = Depends(get_db),
) -> LiveSearchOut:
    candidates = await search_with_cache(q)
    return LiveSearchOut(items=await _to_outs(session, candidates))


class ShelfOut(BaseModel):
    slug: str
    name: str


@router.get("/shelves", response_model=list[ShelfOut], dependencies=[Depends(require_premium)])
async def list_shelves() -> list[ShelfOut]:
    return [ShelfOut(slug=shelf.slug, name=shelf.name) for shelf in SHELVES]


@router.get("/shelves/{slug}", response_model=LiveSearchOut, dependencies=[Depends(require_premium)])
async def shelf_tracks(slug: str, session: AsyncSession = Depends(get_db)) -> LiveSearchOut:
    shelf = get_shelf(slug)
    if shelf is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Полка не найдена")
    candidates = await build_shelf(shelf)
    return LiveSearchOut(items=await _to_outs(session, candidates))


@router.get("/shelves/mix/personal", response_model=LiveSearchOut)
async def personal_mix(
    user: User = Depends(require_premium), session: AsyncSession = Depends(get_db)
) -> LiveSearchOut:
    candidates = await build_personal_mix(session, user.id)
    return LiveSearchOut(items=await _to_outs(session, candidates))


@router.get("/mix/infinity", response_model=LiveSearchOut)
async def infinity_mix(
    live: int = Query(1, ge=0, le=1),
    user: User = Depends(require_premium),
    session: AsyncSession = Depends(get_db),
) -> LiveSearchOut:
    """Бесконечная лента: каталог вперемешку с живыми треками из источника.

    Отдельный маршрут от `/mix` намеренно. `/mix` уважает сохранённые настройки
    рекомендаций, и один выбор «язык = инструментальная» превращал его в вечную
    ленту минусов (жалоба владельца 22.09). Здесь настроек нет вовсе.
    """
    from app.api.security import build_audio_url
    from app.services.infinity_mix import build_infinity_mix

    # ⚠️ live=0 — первая порция: только каталог, без похода в источник. Музыка
    # обязана заиграть мгновенно; живые треки приезжают следующей порцией, пока
    # человек слушает первую. Иначе старт ленты упирался в скорость SoundCloud.
    tracks, candidates = await build_infinity_mix(session, user.id, with_live=bool(live))
    items = [
        LiveTrackOut(
            ref="",
            title=track.title or "",
            artist=track.artist or "",
            duration=track.duration or 0,
            source="db",
            cover_url=track.cover_url,
            track_id=track.id,
            audio_url=build_audio_url(track.id),
        )
        for track in tracks
    ]
    items.extend(await _to_outs(session, candidates))
    return LiveSearchOut(items=items)


@router.post("/search/live/{ref}/fetch")
async def queue_fetch(ref: str, user: User = Depends(require_premium)) -> dict:
    """Ставит фоновую закачку выбранного трека: со второго раза он играет
    мгновенно по file_id и попадает в библиотеку пользователя.

    chat_id не передаём: человек уже слушает поток в плеере, и копия того же
    трека в чате бота ему не нужна — приходила как «бот присылает, хотя я не
    просил». Трек всё равно минтится в архивный чат и падает в библиотеку."""
    candidate = decode_ref(ref)
    if candidate is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ссылка устарела — повторите поиск")
    try:
        from app.tasks.queue_client import enqueue

        enqueue(
            "search.fetch_candidate",
            candidate=asdict(candidate),
            telegram_id=user.telegram_id,
        )
    except Exception:  # noqa: BLE001 — брокер недоступен: поток всё равно играет
        logger.warning("Живой поиск: очередь недоступна", exc_info=True)
        return {"queued": False}
    return {"queued": True}


@router.get("/stream/{ref}")
async def stream_candidate(ref: str, request: Request) -> Response:
    """Проксирует аудиопоток источника. Range пробрасывается как есть — без него
    в Safari и Chrome не работает перемотка."""
    candidate = decode_ref(ref)
    if candidate is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Ссылка недействительна или истекла")

    source_url = await _cached_stream_url(ref, candidate)
    if not source_url:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Источник не отдал поток")

    headers = {}
    if request.headers.get("range"):
        headers["Range"] = request.headers["range"]

    # Таймауты на соединение и паузу между кусками: без них зависший источник
    # держал соединение и память процесса вечно.
    session = aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=None, sock_connect=10, sock_read=30)
    )
    try:
        upstream = await session.get(source_url, headers=headers)
    except Exception:  # noqa: BLE001 — сеть источника
        await session.close()
        _stream_urls.pop(ref, None)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Источник недоступен")
    if upstream.status >= 400:
        upstream.release()
        await session.close()
        _stream_urls.pop(ref, None)  # ссылка источника протухла — следующий раз резолвим заново
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Источник не отдал поток")

    async def body():
        try:
            async for chunk in upstream.content.iter_chunked(_CHUNK):
                yield chunk
        finally:
            upstream.release()
            await session.close()

    passthrough = {
        name: upstream.headers[name]
        for name in ("Content-Length", "Content-Range", "Accept-Ranges")
        if name in upstream.headers
    }
    return StreamingResponse(
        body(),
        status_code=upstream.status,
        media_type=upstream.headers.get("Content-Type", "audio/mpeg"),
        headers={**passthrough, "Cache-Control": "private, max-age=600"},
    )


# --- Альбомы целиком (16.09) ---------------------------------------------------
# Решение владельца: треки альбома слушаются по одному, «добавить весь альбом» —
# с Premium. Mini App и так за пэйволом, поэтому все три маршрута под require_premium.


class LiveAlbumOut(BaseModel):
    id: int
    title: str
    artist: str
    track_count: int
    cover_url: str | None = None
    official: bool = False


_ALBUM_ID_MAX = 10**13  # id SoundCloud — порядка 10^9; шире int64 не пускаем в запрос


async def _album_tracks_or_404(album_id: int) -> list[Candidate]:
    from app.services.albums import album_tracks

    try:
        tracks = await run_in_threadpool(album_tracks, album_id)
    except Exception:  # noqa: BLE001 — источник лёг: честный 404, а не 500
        logger.warning("Альбом %s не открылся", album_id, exc_info=True)
        tracks = []
    if not tracks:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Альбом не найден — повторите поиск")
    return tracks


@router.get("/search/live/albums", response_model=list[LiveAlbumOut], dependencies=[Depends(require_premium)])
async def live_albums(q: str = Query(..., min_length=1, max_length=200)) -> list[LiveAlbumOut]:
    from app.services.albums import search_albums

    try:
        albums = await run_in_threadpool(search_albums, q, 5)
    except Exception:  # noqa: BLE001 — без альбомов поиск треков всё равно работает
        logger.warning("Поиск альбомов не удался: %s", q, exc_info=True)
        return []
    return [
        LiveAlbumOut(
            id=a.id, title=a.title, artist=a.artist, track_count=a.track_count,
            cover_url=a.cover_url, official=a.official,
        )
        for a in albums
    ]


@router.get("/albums/live/{album_id}", response_model=LiveSearchOut, dependencies=[Depends(require_premium)])
async def live_album_tracks(album_id: int, session: AsyncSession = Depends(get_db)) -> LiveSearchOut:
    if not 0 < album_id < _ALBUM_ID_MAX:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Альбом не найден")
    tracks = await _album_tracks_or_404(album_id)
    return LiveSearchOut(items=await _to_outs(session, tracks))


@router.post("/albums/live/{album_id}/library")
async def add_live_album(album_id: int, user: User = Depends(require_premium)) -> dict:
    """Весь альбом в библиотеку: воркер импортирует треки по одному, в чат не шлёт.

    Один альбом за раз на человека — тот же замок, что у кнопки в боте.
    """
    from app.services.albums import acquire_album_lock, estimate_minutes, release_album_lock

    if not 0 < album_id < _ALBUM_ID_MAX:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Альбом не найден")
    tracks = await _album_tracks_or_404(album_id)
    if not acquire_album_lock(user.telegram_id):
        raise HTTPException(status.HTTP_409_CONFLICT, "Альбом уже добавляется — дождитесь окончания")
    try:
        from app.tasks.queue_client import enqueue

        enqueue(
            "album.fetch_all",
            album={"id": album_id, "title": ""},
            tracks=[asdict(track) for track in tracks],
            telegram_id=user.telegram_id,
            chat_id=None,
        )
    except Exception:  # noqa: BLE001 — брокер недоступен: снимаем замок и говорим честно
        release_album_lock(user.telegram_id)
        logger.warning("Альбом: очередь недоступна", exc_info=True)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Сервис загрузки занят, попробуйте позже") from None
    return {"queued": True, "count": len(tracks), "minutes": estimate_minutes(len(tracks))}

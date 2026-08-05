"""Живой поиск для Mini App: выдача прямо из источников и мгновенное
воспроизведение потоком, пока трек качается в фоне.

Два эндпоинта живут по разным правилам доступа, и это не оплошность:
`/search/live` — обычный JWT, `/stream/{ref}` подписан сам (тег <audio> не умеет
слать Authorization-заголовок — та же причина, что и у /tracks/{id}/audio).
"""
import logging
from dataclasses import asdict

import aiohttp
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.api.deps import get_current_user, get_db
from app.db.models import User
from app.services.candidate_ref import decode_ref, encode_ref
from app.services.search import find_track_by_metadata
from app.services.search_cache import search_with_cache
from app.services.shelves import SHELVES, build_personal_mix, build_shelf, get_shelf
from app.services.stream_url import resolve_stream_url
from app.services.track_lookup.importer import candidate_metadata
from app.services.track_lookup.ranking import Candidate

logger = logging.getLogger(__name__)

router = APIRouter(tags=["live-search"])

_CHUNK = 64 * 1024


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


class LiveSearchOut(BaseModel):
    items: list[LiveTrackOut]


async def _to_out(session: AsyncSession, candidate: Candidate) -> LiveTrackOut:
    artist, title = candidate_metadata(candidate)
    existing = await find_track_by_metadata(session, artist, title)
    return LiveTrackOut(
        ref=encode_ref(candidate),
        title=title,
        artist=artist,
        duration=candidate.duration,
        source=candidate.source,
        cover_url=candidate.cover_url,
        track_id=existing.id if existing else None,
    )


@router.get("/search/live", response_model=LiveSearchOut, dependencies=[Depends(get_current_user)])
async def live_search(
    q: str = Query(..., min_length=1),
    session: AsyncSession = Depends(get_db),
) -> LiveSearchOut:
    candidates = await search_with_cache(q)
    return LiveSearchOut(items=[await _to_out(session, item) for item in candidates])


class ShelfOut(BaseModel):
    slug: str
    name: str


@router.get("/shelves", response_model=list[ShelfOut], dependencies=[Depends(get_current_user)])
async def list_shelves() -> list[ShelfOut]:
    return [ShelfOut(slug=shelf.slug, name=shelf.name) for shelf in SHELVES]


@router.get("/shelves/{slug}", response_model=LiveSearchOut, dependencies=[Depends(get_current_user)])
async def shelf_tracks(slug: str, session: AsyncSession = Depends(get_db)) -> LiveSearchOut:
    shelf = get_shelf(slug)
    if shelf is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Полка не найдена")
    candidates = await build_shelf(shelf)
    return LiveSearchOut(items=[await _to_out(session, item) for item in candidates])


@router.get("/shelves/mix/personal", response_model=LiveSearchOut)
async def personal_mix(
    user: User = Depends(get_current_user), session: AsyncSession = Depends(get_db)
) -> LiveSearchOut:
    candidates = await build_personal_mix(session, user.id)
    return LiveSearchOut(items=[await _to_out(session, item) for item in candidates])


@router.post("/search/live/{ref}/fetch")
async def queue_fetch(ref: str, user: User = Depends(get_current_user)) -> dict:
    """Ставит фоновую закачку выбранного трека: со второго раза он играет
    мгновенно по file_id и попадает в библиотеку пользователя.

    chat_id не передаём: человек уже слушает поток в плеере, и копия того же
    трека в чате бота ему не нужна — приходила как «бот присылает, хотя я не
    просил». Трек всё равно минтится в архивный чат и падает в библиотеку."""
    candidate = decode_ref(ref)
    if candidate is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ссылка устарела — повторите поиск")
    try:
        from app.tasks.search_fetch import search_fetch_candidate

        search_fetch_candidate.delay(
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

    source_url = await run_in_threadpool(resolve_stream_url, candidate)
    if not source_url:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Источник не отдал поток")

    headers = {}
    if request.headers.get("range"):
        headers["Range"] = request.headers["range"]

    session = aiohttp.ClientSession()
    try:
        upstream = await session.get(source_url, headers=headers)
    except Exception:  # noqa: BLE001 — сеть источника
        await session.close()
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Источник недоступен")
    if upstream.status >= 400:
        upstream.release()
        await session.close()
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

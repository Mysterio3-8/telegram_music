"""Отдача байтов трека для Mini App-плеера.

Доступ — по HMAC-подписи с истечением (build_audio_url), не по JWT: <audio src>
не умеет слать заголовки. Range поддержан вручную — без него в Safari/Chrome
не работает перемотка.

🔴 Файл отдаётся с диска кусками (цикл 2, 14.09). Раньше КАЖДЫЙ Range-запрос —
а это каждая перемотка и каждый дозапрос браузера — читал весь трек в память:
двадцать слушателей треков по 8 МБ держали ~160 МБ разом на боксе с 961 МБ,
где воркеры уже падали по OOM. Промах кэша качается из Telegram прямо в файл,
и одна закачка на трек, сколько бы человек ни нажали «play» одновременно.
"""
import asyncio
import io
import logging
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from app.api.security import verify_audio_signature
from app.config import settings
from app.db.base import session_factory
from app.db.models import Instrumental, Track
from app.services.audio_cache import cache_commit, cache_file, cache_get, cache_put, cache_tmp_path
from app.services.bot_api import BotApi
from app.services.library import get_track

logger = logging.getLogger(__name__)

router = APIRouter(tags=["audio"])

_MEDIA_TYPES = {
    "mp3": "audio/mpeg",
    "flac": "audio/flac",
    "wav": "audio/wav",
    "m4a": "audio/mp4",
    "ogg": "audio/ogg",
}
_FILE_CHUNK = 256 * 1024
_CACHE_HEADERS = {"Accept-Ranges": "bytes", "Cache-Control": "private, max-age=3600"}

# Одна закачка из Telegram на ключ: без этого десять одновременных «play» по
# свежему треку тянули файл десять раз.
_download_locks: dict[str, asyncio.Lock] = {}


def _media_type(track: Track) -> str:
    return _MEDIA_TYPES.get((track.format or "mp3").lower(), "audio/mpeg")


async def _download_from_telegram(storage_key: str, tg_file_id: str) -> Path | None:
    lock = _download_locks.setdefault(storage_key, asyncio.Lock())
    try:
        async with lock:
            hit = await run_in_threadpool(cache_file, storage_key)
            if hit is not None:
                return hit  # скачал параллельный запрос, пока ждали
            tmp = await run_in_threadpool(cache_tmp_path, storage_key)
            try:
                async with BotApi() as bot:
                    await bot.download(tg_file_id, destination=tmp)
            except Exception:  # noqa: BLE001
                tmp.unlink(missing_ok=True)
                logger.warning("Не удалось скачать %s из Telegram", storage_key, exc_info=True)
                return None
            return await run_in_threadpool(cache_commit, storage_key, tmp)
    finally:
        if not lock.locked():
            _download_locks.pop(storage_key, None)


async def _audio_file(storage_key: str, storage_path: str | None, tg_file_id: str | None) -> Path | None:
    """Файл аудио на диске: локальный архив → LRU-кэш → закачка из Telegram."""
    if storage_path:
        try:
            from app.storage import get_storage

            storage = get_storage()
            local_path = getattr(storage, "path", None)
            if local_path is not None:
                path = local_path(storage_key)
                if path.is_file():
                    return path
            elif settings.audio_cache_max_mb > 0:
                hit = await run_in_threadpool(cache_file, storage_key)
                if hit is not None:
                    return hit
                data = await run_in_threadpool(storage.load, storage_key)
                await run_in_threadpool(cache_put, storage_key, data)
                hit = await run_in_threadpool(cache_file, storage_key)
                if hit is not None:
                    return hit
        except Exception:  # noqa: BLE001
            logger.warning("Архив недоступен %s", storage_key, exc_info=True)
    if settings.audio_cache_max_mb <= 0 or not tg_file_id:
        return None
    hit = await run_in_threadpool(cache_file, storage_key)
    if hit is not None:
        return hit
    return await _download_from_telegram(storage_key, tg_file_id)


async def _load_audio_bytes(
    storage_key: str, storage_path: str | None, tg_file_id: str | None
) -> bytes | None:
    """Запасной путь, когда кэш выключен (AUDIO_CACHE_MAX_MB=0): байты в памяти."""
    if storage_path:
        try:
            from app.storage import get_storage

            return await run_in_threadpool(get_storage().load, storage_key)
        except Exception:  # noqa: BLE001
            logger.warning("Архив недоступен %s", storage_key, exc_info=True)
    if tg_file_id:
        cached = await run_in_threadpool(cache_get, storage_key)
        if cached is not None:
            return cached
        try:
            buffer = io.BytesIO()
            async with BotApi() as bot:
                await bot.download(tg_file_id, destination=buffer)
            return buffer.getvalue()
        except Exception:  # noqa: BLE001
            logger.warning("Не удалось скачать %s из Telegram", storage_key, exc_info=True)
    return None


# Оживление трека прямо в запросе. Один замок на трек: десять слушателей
# одного мёртвого id не должны запустить десять скачиваний.
_revive_locks: dict[int, asyncio.Lock] = {}
# Сколько ждём воркер. Больше — и человек решит, что приложение зависло; меньше —
# не успевает даже быстрый путь SoundCloud вместе с минтом.
_REVIVE_WAIT_SECONDS = 25.0
_REVIVE_POLL_SECONDS = 1.0


async def _fast_bytes(source_url: str) -> bytes | None:
    """Быстрый путь SoundCloud: прямая ссылка на mp3, без yt-dlp и без ffmpeg.

    ⚠️ Только SoundCloud и только progressive-mp3. Всё остальное (YouTube, HLS)
    тянет yt-dlp с перекодировкой, а ffmpeg в процессе API дважды ронял прод по
    OOM — такую работу делает воркер, а мы его ждём.
    """
    if "soundcloud.com" not in (source_url or "").lower():
        return None
    try:
        from app.services.soundcloud_fast import fast_download

        audio = await run_in_threadpool(fast_download, source_url)
    except Exception:  # noqa: BLE001 — источник лёг: остаётся путь через воркер
        logger.warning("Быстрое оживление не удалось: %s", source_url, exc_info=True)
        return None
    return audio.data if audio is not None else None


async def _revive_track(track_id: int) -> Path | None:
    """Достаёт байты трека, у которого умер file_id, и кладёт их в кэш.

    🔴 Зачем это в запросе, а не «поставили задачу и извинились». Владелец
    22.09: «надо исправить баг то что он пишет восстанавливаю треки попробуйте
    позже, такого вообще не должно быть… если его нет в базе и он не заминченый,
    то пусть загрузится и включится». Раньше здесь был 404 и надпись в Mini App;
    теперь трек доезжает в этом же запросе за пару секунд.
    """
    lock = _revive_locks.setdefault(track_id, asyncio.Lock())
    try:
        async with lock:
            storage_key = f"tracks/{track_id}"
            hit = await run_in_threadpool(cache_file, storage_key)
            if hit is not None:
                return hit  # оживил параллельный запрос, пока ждали замок

            async with session_factory() as session:
                track = await session.get(Track, track_id)
                if track is None:
                    return None
                source_url = track.source_url
                had_file_id = bool(track.tg_file_id)
                if had_file_id:
                    # Гасим мёртвый id: пока он в базе, бот и инлайн будут
                    # отдавать по нему тот же отказ.
                    track.tg_file_id = None
                    track.meta_synced = False
                    await session.commit()

            data = await _fast_bytes(source_url or "")
            if data:
                await run_in_threadpool(cache_put, storage_key, data)
                hit = await run_in_threadpool(cache_file, storage_key)
                if hit is not None:
                    # Минт всё равно нужен: кэш на диске вытесняется, а file_id — нет
                    _enqueue_repair(track_id)
                    return hit

            # Быстрый путь не сработал — просим воркер и ждём его результата
            if not _enqueue_repair(track_id):
                return None
            deadline = asyncio.get_event_loop().time() + _REVIVE_WAIT_SECONDS
            while asyncio.get_event_loop().time() < deadline:
                await asyncio.sleep(_REVIVE_POLL_SECONDS)
                async with session_factory() as session:
                    fresh = await session.get(Track, track_id)
                    file_id = fresh.tg_file_id if fresh else None
                if file_id:
                    return await _download_from_telegram(storage_key, file_id)
            logger.warning("Оживление track=%s не уложилось в ожидание", track_id)
            return None
    finally:
        if not lock.locked():
            _revive_locks.pop(track_id, None)


def _enqueue_repair(track_id: int) -> bool:
    try:
        from app.tasks.queue_client import enqueue

        enqueue("search.repair_track", track_id=track_id)
        return True
    except Exception:  # noqa: BLE001 — брокер лёг: вылечим при следующем обращении
        logger.warning("Не удалось поставить восстановление track=%s", track_id, exc_info=True)
        return False


def _parse_range(range_header: str, size: int) -> tuple[int, int]:
    """Единственный диапазон bytes=start-end; всё прочее — 416."""
    try:
        unit, _, spec = range_header.partition("=")
        if unit.strip() != "bytes" or "," in spec:
            raise ValueError
        start_raw, _, end_raw = spec.partition("-")
        if not start_raw.strip():
            # bytes=-N — ПОСЛЕДНИЕ N байт (RFC 9110 §14.1.2). Раньше читалось как
            # 0-N: плеер, спрашивающий хвост файла (теги, индекс m4a), получал начало.
            suffix = int(end_raw)
            if suffix <= 0:
                raise ValueError
            start, end = max(0, size - suffix), size - 1
        else:
            start = int(start_raw)
            end = int(end_raw) if end_raw else size - 1
    except ValueError:
        raise HTTPException(status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE, "Некорректный Range")

    end = min(end, size - 1)
    if start < 0 or start > end or start >= size:
        raise HTTPException(status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE, "Range вне файла")
    return start, end


def _range_response(data: bytes, range_header: str, media_type: str) -> Response:
    """Диапазон поверх байтов в памяти — только для запасного пути без кэша."""
    start, end = _parse_range(range_header, len(data))
    return Response(
        content=data[start : end + 1],
        status_code=status.HTTP_206_PARTIAL_CONTENT,
        media_type=media_type,
        headers={**_CACHE_HEADERS, "Content-Range": f"bytes {start}-{end}/{len(data)}"},
    )


def _file_response(path: Path, range_header: str | None, media_type: str) -> Response:
    # Файл открывается ДО ответа: LRU-кэш может вытеснить его между stat и
    # чтением, а открытый дескриптор на Linux переживает unlink.
    try:
        handle = path.open("rb")
    except OSError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Файл трека недоступен")
    size = os.fstat(handle.fileno()).st_size
    try:
        if range_header:
            start, end = _parse_range(range_header, size)
            status_code = status.HTTP_206_PARTIAL_CONTENT
            headers = {**_CACHE_HEADERS, "Content-Range": f"bytes {start}-{end}/{size}"}
        else:
            start, end = 0, size - 1
            status_code = status.HTTP_200_OK
            headers = dict(_CACHE_HEADERS)
    except HTTPException:
        handle.close()
        raise
    headers["Content-Length"] = str(end - start + 1)

    async def body():
        try:
            await run_in_threadpool(handle.seek, start)
            remaining = end - start + 1
            while remaining > 0:
                chunk = await run_in_threadpool(handle.read, min(_FILE_CHUNK, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk
        finally:
            handle.close()

    return StreamingResponse(body(), status_code=status_code, media_type=media_type, headers=headers)


def _accel_redirect(path: Path, media_type: str) -> Response | None:
    """Ответ-указание nginx отдать файл кэша самому (цикл 6, 14.09).

    Даже кусками по 256 КБ байты гнал Python: каждый поток слушателя — это
    итерации event loop и поток из пула на каждый кусок, на единственном ядре.
    nginx отдаёт файл через sendfile и сам разбирает Range.

    Только для файлов, лежащих прямо в каталоге кэша: имя в заголовке — это путь
    внутри internal-location, и ничего за его пределами туда попасть не должно."""
    prefix = settings.audio_accel_redirect_prefix
    if not prefix:
        return None
    try:
        if path.resolve().parent != Path(settings.audio_cache_dir).resolve():
            return None
    except OSError:
        return None
    # Accept-Ranges ставит nginx сам — из API он приходил вторым заголовком
    return Response(
        status_code=status.HTTP_200_OK,
        headers={
            "Cache-Control": _CACHE_HEADERS["Cache-Control"],
            "X-Accel-Redirect": f"{prefix.rstrip('/')}/{path.name}",
            "Content-Type": media_type,
        },
    )


async def _serve(
    storage_key: str,
    storage_path: str | None,
    tg_file_id: str | None,
    range_header: str | None,
    media_type: str,
) -> Response | None:
    path = await _audio_file(storage_key, storage_path, tg_file_id)
    if path is not None:
        accel = _accel_redirect(path, media_type)
        if accel is not None:
            return accel
        return _file_response(path, range_header, media_type)
    if settings.audio_cache_max_mb > 0:
        return None  # кэш включён, а файла нет — закачка уже не удалась
    data = await _load_audio_bytes(storage_key, storage_path, tg_file_id)
    if data is None:
        return None
    if range_header:
        return _range_response(data, range_header, media_type)
    return Response(content=data, media_type=media_type, headers=_CACHE_HEADERS)


@router.get("/tracks/{track_id}/audio")
async def stream_track_audio(
    track_id: int,
    request: Request,
    exp: int = Query(...),
    sig: str = Query(...),
) -> Response:
    if not verify_audio_signature(track_id, exp, sig):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Ссылка недействительна или истекла")

    # Без DI-цепочки get_db/JWT: запрос уже авторизован подписью
    async with session_factory() as session:
        track = await get_track(session, track_id)
    if track is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Трек не найден")

    response = await _serve(
        f"tracks/{track.id}",
        track.storage_path,
        track.tg_file_id,
        request.headers.get("range"),
        _media_type(track),
    )
    if response is None:
        # Байтов нет и архива нет — мёртвый file_id от старого бота либо трек,
        # который так и не заминтился. Оживляем прямо здесь: человек ждёт
        # секунды и слышит трек, вместо «попробуйте позже».
        path = await _revive_track(track.id)
        if path is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Файл трека недоступен")
        accel = _accel_redirect(path, _media_type(track))
        return accel if accel is not None else _file_response(
            path, request.headers.get("range"), _media_type(track)
        )
    return response


@router.get("/instrumentals/{instrumental_id}/audio")
async def stream_instrumental_audio(
    instrumental_id: int,
    request: Request,
    exp: int = Query(...),
    sig: str = Query(...),
) -> Response:
    """Минусы для Mini App (микс «Инструментальная») — та же схема, что и треки."""
    if not verify_audio_signature(instrumental_id, exp, sig, kind="ins"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Ссылка недействительна или истекла")

    async with session_factory() as session:
        instrumental = await session.get(Instrumental, instrumental_id)
    if instrumental is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Минус не найден")

    # формат в instrumentals не хранится; минусы — mp3
    response = await _serve(
        f"instrumentals/{instrumental.id}",
        instrumental.storage_path,
        instrumental.tg_file_id,
        request.headers.get("range"),
        "audio/mpeg",
    )
    if response is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Файл минуса недоступен")
    return response

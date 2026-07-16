"""Тексты песен (доп. ТЗ): хранение + автопоиск через LRCLIB (свободный API,
без ключа) + ручное добавление пользователями. LRCLIB отдаёт plainLyrics;
недоступность источника не роняет запрос (graceful-фолбэк)."""
import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import aiohttp
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Lyrics, Track

logger = logging.getLogger(__name__)

LRCLIB_API = "https://lrclib.net/api/get"
LRCLIB_TIMEOUT_SEC = 8


@dataclass(frozen=True)
class LyricsResult:
    text: str | None
    source: str | None

    @property
    def found(self) -> bool:
        return bool(self.text)


async def _fetch_lrclib(artist: str, title: str, duration: int | None) -> str | None:
    params = {"artist_name": artist, "track_name": title}
    if duration:
        params["duration"] = str(duration)
    try:
        timeout = aiohttp.ClientTimeout(total=LRCLIB_TIMEOUT_SEC)
        async with aiohttp.ClientSession(timeout=timeout) as http:
            async with http.get(LRCLIB_API, params=params) as response:
                if response.status != 200:
                    return None
                data = await response.json()
                text = (data.get("plainLyrics") or "").strip()
                return text or None
    except (aiohttp.ClientError, asyncio.TimeoutError):
        logger.info("LRCLIB недоступен для «%s — %s»", artist, title)
        return None


async def get_stored_lyrics(session: AsyncSession, track_id: int) -> Lyrics | None:
    return await session.get(Lyrics, track_id)


async def get_or_fetch_lyrics(session: AsyncSession, track: Track) -> LyricsResult:
    """Возвращает сохранённый текст; если его нет — пробует LRCLIB и кэширует."""
    existing = await session.get(Lyrics, track.id)
    if existing is not None:
        return LyricsResult(text=existing.text, source=existing.source)

    text = await _fetch_lrclib(track.artist, track.title, track.duration)
    if text is None:
        return LyricsResult(text=None, source=None)

    await save_lyrics(session, track.id, text, source="lrclib")
    return LyricsResult(text=text, source="lrclib")


async def save_lyrics(
    session: AsyncSession, track_id: int, text: str, source: str = "user"
) -> Lyrics:
    """Создаёт или обновляет текст трека."""
    row = await session.get(Lyrics, track_id)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if row is None:
        row = Lyrics(track_id=track_id, text=text, source=source, updated_at=now)
        session.add(row)
    else:
        row.text = text
        row.source = source
        row.updated_at = now
    await session.commit()
    return row

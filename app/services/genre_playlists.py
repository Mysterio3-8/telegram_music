"""Плейлисты «редакции» по жанрам (SPEC-КАТАЛОГ §5): автогенерация от
админ-пользователя — раздел «Кураторы» Mini App и карточки жанров наполняются
сразу, без ручной работы.

Идемпотентно: плейлист ищется по (user_id, title), состав обновляется целиком —
повторный прогон освежает подборки по мере роста базы.
"""
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Genre, Playlist, PlaylistTrack
from app.services.genres import genre_tracks

MIN_TRACKS = 10  # жанр беднее — подборка выглядит пусто, пропускаем
MAX_TRACKS = 50


@dataclass
class GeneratedPlaylist:
    title: str
    track_count: int
    created: bool


async def _upsert_playlist(session: AsyncSession, user_id: int, title: str) -> tuple[Playlist, bool]:
    existing = await session.scalar(
        select(Playlist).where(Playlist.user_id == user_id, Playlist.title == title)
    )
    if existing is not None:
        return existing, False
    playlist = Playlist(user_id=user_id, title=title)
    session.add(playlist)
    await session.flush()
    return playlist, True


async def generate_genre_playlists(
    session: AsyncSession, user_id: int, *, min_tracks: int = MIN_TRACKS, max_tracks: int = MAX_TRACKS
) -> list[GeneratedPlaylist]:
    """Для каждого жанра с достаточным числом треков — плейлист-подборка.
    Идём по всем уровням дерева: поджанр богаче родителя не бывает (наследование),
    бедные уровни отсеются порогом сами."""
    results: list[GeneratedPlaylist] = []
    genres = list((await session.scalars(select(Genre).order_by(Genre.id))).all())
    for genre in genres:
        tracks, total = await genre_tracks(session, genre, 1, max_tracks)
        if total < min_tracks:
            continue
        playlist, created = await _upsert_playlist(session, user_id, genre.name)
        await session.execute(delete(PlaylistTrack).where(PlaylistTrack.playlist_id == playlist.id))
        for position, track in enumerate(tracks, start=1):
            session.add(
                PlaylistTrack(playlist_id=playlist.id, track_id=track.id, position=position)
            )
        await session.commit()
        results.append(GeneratedPlaylist(title=genre.name, track_count=len(tracks), created=created))
    return results

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import Track, Upload, UserLibrary

SUPPORTED_FORMATS = {"mp3", "flac", "wav", "m4a", "ogg"}

# Совпадение метаданных считаем дубликатом при разбеге длительности до 2 секунд.
# Настоящий аудиоотпечаток (chromaprint) появится на Этапе 4 вместе с хранилищем файлов.
DUPLICATE_DURATION_TOLERANCE = 2

_MIME_FORMATS = {
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
    "audio/flac": "flac",
    "audio/x-flac": "flac",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/mp4": "m4a",
    "audio/x-m4a": "m4a",
    "audio/ogg": "ogg",
    "application/ogg": "ogg",
}


@dataclass(frozen=True)
class AudioMeta:
    file_id: str
    file_name: str | None
    mime_type: str | None
    file_size: int | None
    duration: int


def detect_format(file_name: str | None, mime_type: str | None) -> str | None:
    if file_name and "." in file_name:
        extension = file_name.rsplit(".", 1)[1].lower()
        if extension in SUPPORTED_FORMATS:
            return extension
    if mime_type:
        return _MIME_FORMATS.get(mime_type.lower())
    return None


def validate_audio(meta: AudioMeta) -> str | None:
    """Возвращает текст ошибки или None, если файл подходит.
    Аудиофайлы принимаются без ограничения по размеру (решение владельца) — только
    формат и длительность, без которых трек нельзя завести и проиграть."""
    if detect_format(meta.file_name, meta.mime_type) is None:
        return "Неподдерживаемый формат. Принимаются: MP3, FLAC, WAV, M4A, OGG."
    if meta.duration <= 0:
        return "Не удалось определить длительность файла."
    return None


async def count_user_uploads(session: AsyncSession, user_id: int) -> int:
    count = await session.scalar(
        select(func.count()).select_from(Upload).where(Upload.user_id == user_id)
    )
    return count or 0


async def find_duplicate(
    session: AsyncSession, title: str, artist: str, duration: int
) -> Track | None:
    """Тот же трек по «исполнитель — название» и длительности. None — такого нет.

    🔴 Сверка идёт по `search_index`, а НЕ по `lower(title)`, и это принципиально.
    SQLite `lower()` понижает только ASCII — известная грабля этого проекта. Питон
    приводил запрос к «зеркало», а база оставалась с «Зеркало», и сравнение не
    совпадало НИКОГДА, если в названии кириллица. Дедуп при этом молчал, а не
    падал, поэтому выглядело всё исправным.

    Замер 16.08: 140 пар «артист+название» с дублями, у 61 в названии кириллица;
    131 дубль заведён уже после перехода на живой поиск. Живой пример — шесть
    копий «yarik — Зеркало» с ОДНОЙ И ТОЙ ЖЕ ссылкой источника: воспроизведение
    прежнего запроса на этих данных возвращало None.

    `search_index` собирается в Питоне (`build_search_index`), то есть уже
    понижен и транслитерирован; на проде он есть у 7492 треков из 7493.
    """
    from app.services.search_index import build_search_index

    window = Track.duration.between(
        duration - DUPLICATE_DURATION_TOLERANCE,
        duration + DUPLICATE_DURATION_TOLERANCE,
    )
    found = await session.scalar(
        select(Track)
        .where(Track.search_index == build_search_index(artist, title), window)
        .limit(1)
    )
    if found is not None:
        return found
    # Фолбэк на прежнее сравнение — для строк, у которых search_index не заполнен
    # (легаси), и как страховка на случай, если формат индекса когда-нибудь
    # изменится: молча перестать ловить дубликаты хуже, чем поискать дважды.
    return await session.scalar(
        select(Track)
        .where(
            func.lower(Track.title) == title.strip().lower(),
            func.lower(Track.artist) == artist.strip().lower(),
            window,
        )
        .limit(1)
    )


async def find_by_fingerprint(session: AsyncSession, fingerprint: str) -> Track | None:
    """Точный дубликат по акустическому отпечатку — независимо от метаданных."""
    stmt = select(Track).where(Track.fingerprint == fingerprint).limit(1)
    return await session.scalar(stmt)


from app.services.moderation import initial_status


async def create_uploaded_track(
    session: AsyncSession, user_id: int, meta: AudioMeta, title: str, artist: str
) -> Track:
    """Создаёт трек в общей базе, запись о загрузке и кладёт трек в библиотеку автора."""
    bitrate = None
    if meta.file_size and meta.duration > 0:
        bitrate = round(meta.file_size * 8 / meta.duration / 1000)
    track = Track(
        title=title.strip(),
        artist=artist.strip(),
        duration=meta.duration,
        bitrate=bitrate,
        file_size=meta.file_size,
        format=detect_format(meta.file_name, meta.mime_type),
        tg_file_id=meta.file_id,
        moderation_status=initial_status(title, artist),
    )
    session.add(track)
    await session.flush()
    session.add(Upload(user_id=user_id, track_id=track.id))
    session.add(UserLibrary(user_id=user_id, track_id=track.id))
    await session.commit()
    return track

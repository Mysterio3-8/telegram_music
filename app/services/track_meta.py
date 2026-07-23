"""Приведение аудиофайла к актуальным метаданным: ID3-теги и имя файла.

Формат имени — «Исполнитель — Название.mp3» (SPEC: доработки, п.1).
Перетегирование — mutagen; при любой ошибке возвращаем исходные байты,
чтобы выдача файла не ломалась из-за битых тегов (graceful-фолбэк, как fpcalc).
"""
import io
import logging
import re

logger = logging.getLogger(__name__)

_FILENAME_FORBIDDEN = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
MAX_FILENAME_LENGTH = 120


def build_filename(artist: str, title: str, fmt: str | None) -> str:
    """«Исполнитель — Название.mp3», безопасное для файловых систем и Telegram."""
    artist_part = _FILENAME_FORBIDDEN.sub("", artist).strip()
    title_part = _FILENAME_FORBIDDEN.sub("", title).strip()
    stem = " — ".join(part for part in (artist_part, title_part) if part) or "track"
    if len(stem) > MAX_FILENAME_LENGTH:
        stem = stem[:MAX_FILENAME_LENGTH].rstrip()
    return f"{stem}.{(fmt or 'mp3').lower()}"


def retag_audio(data: bytes, fmt: str | None, title: str, artist: str) -> bytes:
    """Обновляет теги (Title/Artist) в аудиофайле. При ошибке — исходные байты."""
    try:
        import mutagen

        buffer = io.BytesIO(data)
        audio = mutagen.File(buffer, easy=True)
        if audio is None:
            return data
        if audio.tags is None:
            audio.add_tags()
        audio["title"] = title.strip()
        audio["artist"] = artist.strip()
        buffer.seek(0)
        audio.save(buffer)
        return buffer.getvalue()
    except Exception:  # noqa: BLE001 — любые проблемы тегов не должны блокировать выдачу
        logger.warning("Не удалось обновить теги (title=%r, artist=%r)", title, artist, exc_info=True)
        return data


def embed_cover(data: bytes, fmt: str | None, image: bytes) -> bytes:
    """Вшивает обложку в аудиофайл (MP3 → APIC, M4A → covr) — Telegram и плееры
    показывают её у трека. При любой ошибке — исходные байты."""
    if not image:
        return data
    mime = "image/png" if image[:8] == b"\x89PNG\r\n\x1a\n" else "image/jpeg"
    try:
        buffer = io.BytesIO(data)
        kind = (fmt or "").lower()
        if kind == "mp3":
            from mutagen.id3 import APIC, ID3, ID3NoHeaderError

            try:
                tags = ID3(buffer)
            except ID3NoHeaderError:
                tags = ID3()
            tags.delall("APIC")
            tags.add(APIC(encoding=3, mime=mime, type=3, desc="Cover", data=image))
            buffer.seek(0)
            tags.save(buffer)
            return buffer.getvalue()
        if kind in ("m4a", "mp4", "aac"):
            from mutagen.mp4 import MP4, MP4Cover

            audio = MP4(buffer)
            image_format = (
                MP4Cover.FORMAT_PNG if mime == "image/png" else MP4Cover.FORMAT_JPEG
            )
            audio["covr"] = [MP4Cover(image, imageformat=image_format)]
            buffer.seek(0)
            audio.save(buffer)
            return buffer.getvalue()
        return data  # ogg/flac и прочее — без обложки, не ломаем файл
    except Exception:  # noqa: BLE001 — обложка не должна блокировать импорт
        logger.warning("Не удалось вшить обложку (fmt=%r)", fmt, exc_info=True)
        return data

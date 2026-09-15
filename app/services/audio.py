import tempfile
from pathlib import Path

from mutagen import File as MutagenFile


def duration_from_path(path: str | Path) -> int:
    """Длительность аудиофайла в секундах. 0, если определить не удалось."""
    try:
        audio = MutagenFile(str(path))
    except Exception:  # noqa: BLE001 — битый файл: mutagen бросает свои HeaderNotFound и т.п.
        return 0
    if audio is None or audio.info is None:
        return 0
    return int(audio.info.length)


def duration_from_bytes(data: bytes, suffix: str) -> int:
    """Длительность аудио в секундах из байтов. 0, если определить не удалось."""
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(data)
        tmp_path = tmp.name
    try:
        return duration_from_path(tmp_path)
    finally:
        Path(tmp_path).unlink(missing_ok=True)

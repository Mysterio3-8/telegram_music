import tempfile
from pathlib import Path

from mutagen import File as MutagenFile


def duration_from_bytes(data: bytes, suffix: str) -> int:
    """Длительность аудио в секундах из байтов. 0, если определить не удалось."""
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(data)
        tmp_path = tmp.name
    try:
        audio = MutagenFile(tmp_path)
        if audio is None or audio.info is None:
            return 0
        return int(audio.info.length)
    finally:
        Path(tmp_path).unlink(missing_ok=True)

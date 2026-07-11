import logging
from collections.abc import Iterator
from pathlib import Path

from mutagen import File as MutagenFile

from app.importers.base import ImportItem
from app.services.uploads import SUPPORTED_FORMATS

logger = logging.getLogger(__name__)


class LocalDirectorySource:
    """Импорт аудиофайлов из локального каталога (рекурсивно)."""

    def __init__(self, directory: str) -> None:
        self._directory = Path(directory)

    def items(self) -> Iterator[ImportItem]:
        for path in sorted(self._directory.rglob("*")):
            if not path.is_file() or path.suffix.lstrip(".").lower() not in SUPPORTED_FORMATS:
                continue
            item = self._read(path)
            if item is not None:
                yield item

    def _read(self, path: Path) -> ImportItem | None:
        try:
            audio = MutagenFile(path, easy=True)
        except Exception as exc:  # повреждённый файл — пропускаем, не роняем импорт
            logger.warning("Не прочитан %s: %s", path.name, exc)
            return None
        if audio is None or audio.info is None:
            logger.warning("Неподдерживаемый файл: %s", path.name)
            return None

        title = (audio.get("title") or [path.stem])[0]
        artist = (audio.get("artist") or ["Unknown"])[0]
        return ImportItem(
            title=title,
            artist=artist,
            duration=int(audio.info.length),
            data=path.read_bytes(),
            file_format=path.suffix.lstrip(".").lower(),
        )

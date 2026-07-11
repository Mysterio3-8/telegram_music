"""Массовый импорт каталога из локального каталога файлов.

Использование:
    python -m app.cli.import_catalog <директория> [--instrumental]
"""
import argparse
import asyncio
import logging

from app.db.base import session_factory
from app.importers.local_dir import LocalDirectorySource
from app.services.catalog_import import import_instrumental, import_track
from app.storage import get_storage

logger = logging.getLogger("import")


async def run(directory: str, as_instrumental: bool, default_artist: str) -> None:
    source = LocalDirectorySource(directory, default_artist=default_artist)
    storage = get_storage()
    importer = import_instrumental if as_instrumental else import_track

    created = 0
    skipped = 0
    async with session_factory() as session:
        for item in source.items():
            if await importer(session, storage, item):
                created += 1
                logger.info("Импортирован: %s — %s", item.artist, item.title)
            else:
                skipped += 1
                logger.info("Дубликат, пропущен: %s — %s", item.artist, item.title)

    logger.info("Готово. Добавлено: %s, пропущено дубликатов: %s", created, skipped)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Импорт аудиокаталога в общую базу")
    parser.add_argument("directory", help="Путь к каталогу с аудиофайлами")
    parser.add_argument(
        "--instrumental", action="store_true", help="Импортировать как минусы (instrumentals)"
    )
    parser.add_argument(
        "--artist", default="Unknown", help="Исполнитель для файлов без ID3-тега artist"
    )
    args = parser.parse_args()
    asyncio.run(run(args.directory, args.instrumental, args.artist))


if __name__ == "__main__":
    main()

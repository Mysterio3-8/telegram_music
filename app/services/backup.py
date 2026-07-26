"""Резервное копирование БД (блок G): консистентный снимок + ротация.

Страх владельца — «бот слетит, всё пропадёт». Ежедневный таймер снимает копию
БД в backup_dir и удаляет старые, оставляя последние backup_keep штук.

SQLite: онлайн-бэкап через sqlite3 (консистентно даже при живой записи бота).
PostgreSQL: снимок делает pg_dump (см. функцию — вызывает системный pg_dump).
"""
import logging
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)


def _sqlite_path() -> str | None:
    url = settings.database_url
    if not url.startswith("sqlite"):
        return None
    # sqlite+aiosqlite:///music_bot.db → music_bot.db
    return url.split(":///", 1)[1] if ":///" in url else url.rsplit("/", 1)[-1]


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def _prune(backup_dir: Path, keep: int) -> int:
    backups = sorted(backup_dir.glob("db-*.*"), key=lambda p: p.stat().st_mtime, reverse=True)
    removed = 0
    for old in backups[keep:]:
        old.unlink(missing_ok=True)
        removed += 1
    return removed


def create_backup() -> Path:
    """Делает снимок БД, чистит старые, возвращает путь к копии."""
    backup_dir = Path(settings.backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)

    sqlite_path = _sqlite_path()
    if sqlite_path:
        target = backup_dir / f"db-{_timestamp()}.sqlite"
        source = sqlite3.connect(sqlite_path)
        try:
            dest = sqlite3.connect(str(target))
            try:
                source.backup(dest)  # онлайн-бэкап, консистентный снимок
            finally:
                dest.close()
        finally:
            source.close()
    else:
        # PostgreSQL — снимок через pg_dump (сжатый custom-формат)
        target = backup_dir / f"db-{_timestamp()}.dump"
        subprocess.run(
            ["pg_dump", "--format=custom", "--file", str(target), settings.database_url],
            check=True,
        )

    removed = _prune(backup_dir, settings.backup_keep)
    logger.info("Бэкап БД создан: %s (удалено старых: %s)", target, removed)
    return target

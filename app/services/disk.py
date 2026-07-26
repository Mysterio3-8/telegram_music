"""Защита от переполнения диска (инцидент 2026-07-26).

Когда диск забивается под ноль, Redis перестаёт делать снимки → блокирует запись →
падает FSM бота. Поэтому скачивание и кэш не должны доедать последние мегабайты:
качаем только пока свободно ≥ min_free_disk_mb.
"""
import logging
import shutil

from app.config import settings

logger = logging.getLogger(__name__)


def free_mb(path: str = ".") -> int:
    """Свободно на диске, МБ. Не смогли измерить → большое число (не блокируем)."""
    try:
        return shutil.disk_usage(path).free // (1024 * 1024)
    except OSError:
        return 10**9


def enough_free_disk() -> bool:
    """True — места достаточно, можно качать/писать на диск."""
    ok = free_mb() >= settings.min_free_disk_mb
    if not ok:
        logger.warning("Мало места на диске (%s МБ) — пропускаю запись/скачивание", free_mb())
    return ok

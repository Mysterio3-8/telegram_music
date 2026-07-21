"""LRU-кэш байтов аудио на диске.

Стрим Mini App для треков без архивной копии качает файл у Telegram на каждый
плей — это медленный старт и лишний трафик. Кэш держит горячие байты на диске
в пределах audio_cache_max_mb; старое вытесняется по времени последнего
обращения (mtime). Ошибки диска не роняют стрим — кэш просто промахивается.
"""
import logging
import os
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)


def _cache_path(storage_key: str) -> Path:
    # "tracks/123" → "tracks_123": плоский каталог без вложенности
    return Path(settings.audio_cache_dir) / storage_key.replace("/", "_")


def cache_get(storage_key: str) -> bytes | None:
    if settings.audio_cache_max_mb <= 0:
        return None
    path = _cache_path(storage_key)
    try:
        data = path.read_bytes()
    except OSError:
        return None
    try:
        os.utime(path, None)  # LRU-отметка «недавно использован»
    except OSError:
        pass
    return data


def cache_put(storage_key: str, data: bytes) -> None:
    if settings.audio_cache_max_mb <= 0:
        return
    path = _cache_path(storage_key)
    tmp = path.with_name(path.name + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_bytes(data)
        tmp.replace(path)
    except OSError:
        logger.warning("Не удалось записать аудио-кэш %s", storage_key, exc_info=True)
        return
    _evict_lru()


def _evict_lru() -> None:
    limit = settings.audio_cache_max_mb * 1024 * 1024
    root = Path(settings.audio_cache_dir)
    entries: list[tuple[float, int, Path]] = []
    try:
        for file in root.iterdir():
            if not file.is_file():
                continue
            stat = file.stat()
            entries.append((stat.st_mtime, stat.st_size, file))
    except OSError:
        return

    total = sum(size for _, size, _ in entries)
    for _, size, file in sorted(entries):
        if total <= limit:
            break
        try:
            file.unlink()
        except OSError:
            continue
        total -= size

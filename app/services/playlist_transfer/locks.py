"""Потолок и замок переноса плейлиста.

Отдельно от service.py (цикл 7, 15.09): API Mini App ставит перенос и держит
замок, а сам перенос идёт в воркере. service.py тянет aiogram и yt-dlp — процессу
API они не нужны.
"""
import logging

from app.config import settings

logger = logging.getLogger(__name__)

# Потолок одного переноса (решение владельца). Перенос идёт последовательно с
# паузой 5–60 сек между скачиваниями, так что 1000 треков — это до полусуток.
TRANSFER_MAX_ITEMS = 1000

# Один активный перенос на человека: без замка десять отправок подряд ставили
# десять многочасовых задач, и очередь стояла у всех.
_LOCK_PREFIX = "transfer:active:"
_LOCK_TTL_SECONDS = 24 * 3600


def _redis_sync():
    if not settings.redis_url:
        return None
    try:
        import redis

        return redis.from_url(settings.redis_url)
    except Exception:  # noqa: BLE001 — замок опционален, как и кэш поиска
        logger.warning("Перенос: Redis недоступен, замок не ставится", exc_info=True)
        return None


def acquire_transfer_lock(telegram_id: int) -> bool:
    """True — можно начинать. Redis недоступен → не блокируем: перенос важнее замка."""
    client = _redis_sync()
    if client is None:
        return True
    try:
        return bool(
            client.set(f"{_LOCK_PREFIX}{telegram_id}", "1", nx=True, ex=_LOCK_TTL_SECONDS)
        )
    except Exception:  # noqa: BLE001
        logger.warning("Перенос: не удалось поставить замок", exc_info=True)
        return True


def release_transfer_lock(telegram_id: int) -> None:
    client = _redis_sync()
    if client is None:
        return
    try:
        client.delete(f"{_LOCK_PREFIX}{telegram_id}")
    except Exception:  # noqa: BLE001 — истечёт сам по TTL
        logger.warning("Перенос: не удалось снять замок", exc_info=True)

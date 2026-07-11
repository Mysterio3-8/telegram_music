import logging

from aiogram.fsm.storage.base import BaseStorage
from aiogram.fsm.storage.memory import MemoryStorage

from app.config import settings

logger = logging.getLogger(__name__)


def build_storage() -> BaseStorage:
    """Redis-хранилище FSM, если задан redis_url; иначе in-memory."""
    if not settings.redis_url:
        logger.info("FSM storage: in-memory (redis_url не задан)")
        return MemoryStorage()

    from aiogram.fsm.storage.redis import RedisStorage

    logger.info("FSM storage: Redis")
    return RedisStorage.from_url(settings.redis_url)

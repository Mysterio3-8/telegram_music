import asyncio
import logging

from aiogram.fsm.storage.base import BaseStorage
from aiogram.fsm.storage.memory import MemoryStorage

from app.config import settings

logger = logging.getLogger(__name__)

# Столько ждём ответа Redis на старте. Секунда с запасом: он на этой же машине,
# и живой отвечает за миллисекунды. Дольше ждать нечего — цена ошибки здесь
# в том, что бот не поднимается вообще.
_PING_TIMEOUT = 1.0


async def build_storage() -> BaseStorage:
    """Redis-хранилище FSM, если задан redis_url и Redis отвечает; иначе in-memory.

    ⚠️ Проверка связи обязательна, и вот почему. Раньше фолбэк на память
    срабатывал ТОЛЬКО когда redis_url не задан, а `RedisStorage.from_url`
    соединение не открывает — оно ленивое. То есть при живом конфиге и мёртвом
    Redis бот считался запущенным, но падал на КАЖДОЙ команде: FSM-хранилище
    недоступно. Ровно это было 26.07 — диск заполнился до 100%, Redis не смог
    записать снимок, включил stop-writes-on-bgsave-error и перестал принимать
    запись; снаружи это выглядело как «бот не отвечает на /start».

    Память вместо Redis — это потеря состояния мастеров (загрузка трека, ввод
    поиска) при рестарте и невидимость состояния между процессами. Плохо, но
    несравнимо лучше бота, который не работает совсем: диалоговые мастера здесь
    короткие, а всё остальное состояние живёт в БД.
    """
    if not settings.redis_url:
        logger.info("FSM storage: in-memory (redis_url не задан)")
        return MemoryStorage()

    from aiogram.fsm.storage.redis import RedisStorage

    storage = RedisStorage.from_url(settings.redis_url)
    try:
        await asyncio.wait_for(storage.redis.ping(), timeout=_PING_TIMEOUT)
    except Exception as exc:  # сеть, таймаут, отказ в записи, неверный url
        # Закрываем неудавшийся клиент: иначе висит пул соединений, который
        # никто уже не использует.
        try:
            await storage.close()
        except Exception:  # noqa: BLE001 — закрытие мёртвого клиента не должно мешать старту
            pass
        logger.error(
            "FSM storage: Redis по %s не отвечает (%s) — перехожу на in-memory. "
            "Бот работает, но состояние мастеров теряется при рестарте. "
            "Проверь: systemctl status redis-server, свободное место на диске "
            "(при 100%% Redis запрещает запись).",
            settings.redis_url,
            exc,
        )
        return MemoryStorage()

    logger.info("FSM storage: Redis")
    return storage

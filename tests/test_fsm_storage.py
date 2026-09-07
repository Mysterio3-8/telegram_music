"""Бот должен подниматься даже когда Redis лёг.

Зачем: `RedisStorage.from_url` соединение не открывает — оно ленивое. Поэтому
при заданном redis_url и мёртвом Redis бот раньше считался запущенным, а падал
на КАЖДОЙ команде: FSM-хранилище недоступно. Так выглядел инцидент 26.07 —
диск заполнился, Redis запретил себе запись, а снаружи это читалось как
«бот не отвечает на /start».
"""
import pytest
from aiogram.fsm.storage.memory import MemoryStorage

from app import fsm


@pytest.mark.asyncio
async def test_memory_storage_when_redis_url_is_empty(monkeypatch):
    monkeypatch.setattr(fsm.settings, "redis_url", "")
    assert isinstance(await fsm.build_storage(), MemoryStorage)


@pytest.mark.asyncio
async def test_falls_back_to_memory_when_redis_is_unreachable(monkeypatch):
    # Порт, на котором заведомо никто не слушает: имитируем лежащий Redis.
    monkeypatch.setattr(fsm.settings, "redis_url", "redis://127.0.0.1:6399/0")
    storage = await fsm.build_storage()
    assert isinstance(storage, MemoryStorage), "мёртвый Redis не должен мешать боту стартовать"


@pytest.mark.asyncio
async def test_uses_redis_when_it_answers(monkeypatch):
    from aiogram.fsm.storage.redis import RedisStorage

    monkeypatch.setattr(fsm.settings, "redis_url", "redis://127.0.0.1:6379/0")

    async def ok_ping():
        return True

    real_from_url = RedisStorage.from_url

    def patched_from_url(url, **kwargs):
        storage = real_from_url(url, **kwargs)
        monkeypatch.setattr(storage.redis, "ping", ok_ping)
        return storage

    monkeypatch.setattr(RedisStorage, "from_url", staticmethod(patched_from_url))

    storage = await fsm.build_storage()
    assert isinstance(storage, RedisStorage), "живой Redis должен использоваться как раньше"
    await storage.close()


@pytest.mark.asyncio
async def test_slow_redis_does_not_hang_startup(monkeypatch):
    """Redis, который не отвечает (а не отказывает), не должен вешать запуск."""
    import asyncio

    from aiogram.fsm.storage.redis import RedisStorage

    monkeypatch.setattr(fsm.settings, "redis_url", "redis://127.0.0.1:6379/0")
    monkeypatch.setattr(fsm, "_PING_TIMEOUT", 0.05)

    async def hanging_ping():
        await asyncio.sleep(30)

    real_from_url = RedisStorage.from_url

    def patched_from_url(url, **kwargs):
        storage = real_from_url(url, **kwargs)
        monkeypatch.setattr(storage.redis, "ping", hanging_ping)
        return storage

    monkeypatch.setattr(RedisStorage, "from_url", staticmethod(patched_from_url))

    storage = await asyncio.wait_for(fsm.build_storage(), timeout=5)
    assert isinstance(storage, MemoryStorage), "зависший Redis должен отваливаться по таймауту"

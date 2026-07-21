import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.db import models  # noqa: F401 — регистрирует таблицы в metadata до create_all
from app.db.base import Base


@pytest.fixture(autouse=True)
def _tmp_storage(tmp_path, monkeypatch):
    """Хранилище и аудио-кэш — во временный каталог: тесты не пишут в рабочий."""
    monkeypatch.setattr(settings, "storage_dir", str(tmp_path / "storage"))
    monkeypatch.setattr(settings, "audio_cache_dir", str(tmp_path / "audio_cache"))
    # Анти-бан-паузы SoundCloud (5-60 сек) в тестах не нужны
    monkeypatch.setattr(settings, "soundcloud_min_delay", 0.0)
    monkeypatch.setattr(settings, "soundcloud_max_delay", 0.0)


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db_session:
        yield db_session
    await engine.dispose()

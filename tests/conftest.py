import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import models  # noqa: F401 — регистрирует таблицы в metadata до create_all
from app.db.base import Base


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db_session:
        yield db_session
    await engine.dispose()

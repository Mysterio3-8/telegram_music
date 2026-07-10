from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(settings.database_url)
session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db() -> None:
    from app.db import models  # noqa: F401 — регистрирует таблицы в metadata до create_all

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

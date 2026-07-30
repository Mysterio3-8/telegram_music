from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


class Base(DeclarativeBase):
    pass


def _set_sqlite_pragma(dbapi_connection, _connection_record) -> None:
    """Один файл SQLite делят бот + API + несколько Celery-воркеров одновременно.
    По умолчанию (journal_mode=DELETE) писатель блокирует читателей и наоборот —
    под конкурентной нагрузкой это «database is locked» (падение хендлера) и
    лаги. WAL: читатели не блокируют писателя. busy_timeout: если блокировка
    всё же случилась — подождать (до 30 сек), а не упасть немедленно."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


def _new_engine():
    """Общая точка создания движка: гарантирует, что PRAGMA применены везде,
    где есть свой engine (бот/API и каждая Celery-задача с отдельным event loop)."""
    new_engine = create_async_engine(settings.database_url)
    if settings.database_url.startswith("sqlite"):
        event.listens_for(new_engine.sync_engine, "connect")(_set_sqlite_pragma)
    return new_engine


def build_task_engine():
    """Отдельный engine+session_factory для Celery-задачи. Каждая задача крутит
    свой asyncio.run() в своём потоке — движок бота/API (с его event loop)
    сюда не годится, нужен новый на каждый вызов, но с теми же PRAGMA."""
    task_engine = _new_engine()
    return task_engine, async_sessionmaker(task_engine, expire_on_commit=False)


engine = _new_engine()
session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# Схема управляется Alembic-миграциями (`alembic upgrade head`), не create_all.

"""Бэкфилл архивных копий: треки/минусы, заминченные через бота без storage_path.

Скачивает байты у Telegram (Bot API отдаёт файлы ≤ 20 МБ) и кладёт в хранилище —
после этого стрим Mini App идёт из архива, а не через bot.download на каждый плей.
Файлы больше лимита пропускаются с подсчётом: их вернёт только повторный импорт
из первоисточника.

Запуск: python -m app.cli.backfill_archives [--limit N] [--dry]
"""
import argparse
import asyncio
import io
import logging

from aiogram import Bot
from sqlalchemy import select

from app.config import settings
from app.db.base import session_factory
from app.db.models import Instrumental, Track
from app.storage import get_storage

logger = logging.getLogger(__name__)

# getFile отказывает на файлах ~>20 МБ; чуть ниже порога, чтобы не ловить отказ впустую
BOT_API_DOWNLOAD_LIMIT = 20 * 1024 * 1024


async def _download(bot: Bot, tg_file_id: str) -> bytes | None:
    try:
        buffer = io.BytesIO()
        await bot.download(tg_file_id, destination=buffer)
        return buffer.getvalue()
    except Exception:  # noqa: BLE001
        return None


async def backfill(limit: int, dry: bool) -> None:
    async with session_factory() as session:
        tracks = (
            await session.scalars(
                select(Track)
                .where(Track.storage_path.is_(None), Track.tg_file_id.is_not(None))
                .limit(limit)
            )
        ).all()
        instrumentals = (
            await session.scalars(
                select(Instrumental)
                .where(Instrumental.storage_path.is_(None), Instrumental.tg_file_id.is_not(None))
                .limit(limit)
            )
        ).all()

        oversize = [t for t in tracks if (t.file_size or 0) > BOT_API_DOWNLOAD_LIMIT]
        tracks = [t for t in tracks if (t.file_size or 0) <= BOT_API_DOWNLOAD_LIMIT]
        print(f"Кандидатов: треков {len(tracks)}, минусов {len(instrumentals)}; "
              f"пропущено >20 МБ: {len(oversize)}")
        if dry:
            return

        storage = get_storage()
        bot = Bot(token=settings.bot_token)
        saved = failed = 0
        try:
            for entity, key_prefix in [
                *((t, "tracks") for t in tracks),
                *((i, "instrumentals") for i in instrumentals),
            ]:
                data = await _download(bot, entity.tg_file_id)
                if data is None:
                    failed += 1
                    continue
                entity.storage_path = storage.save(f"{key_prefix}/{entity.id}", data)
                await session.commit()
                saved += 1
        finally:
            await bot.session.close()
        print(f"Сохранено в архив: {saved}, ошибок скачивания: {failed}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=10000, help="максимум записей за прогон")
    parser.add_argument("--dry", action="store_true", help="только посчитать, ничего не качать")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    asyncio.run(backfill(args.limit, args.dry))


if __name__ == "__main__":
    main()

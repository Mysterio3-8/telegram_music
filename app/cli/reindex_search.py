"""Бэкфилл поискового индекса треков.

  python -m app.cli.reindex_search           # только треки без индекса
  python -m app.cli.reindex_search --all     # пересчитать всем (после смены правил)

Без индекса поиск по кириллице на SQLite не работает (lower/ILIKE — ASCII-only),
поэтому после деплоя прогон обязателен.
"""
import argparse
import asyncio

from sqlalchemy import select

from app.db.base import session_factory
from app.db.models import Track
from app.services.search_index import build_search_index

BATCH = 500


async def _reindex(rebuild_all: bool) -> None:
    updated = 0
    async with session_factory() as session:
        while True:
            stmt = select(Track).order_by(Track.id).limit(BATCH)
            if not rebuild_all:
                stmt = stmt.where(Track.search_index.is_(None))
            else:
                stmt = stmt.offset(updated)
            tracks = list((await session.scalars(stmt)).all())
            if not tracks:
                break
            for track in tracks:
                track.search_index = build_search_index(track.artist, track.title)
            await session.commit()
            updated += len(tracks)
            print(f"…проиндексировано {updated}")
    print(f"Готово: {updated} треков")


def main() -> None:
    parser = argparse.ArgumentParser(description="Бэкфилл поискового индекса")
    parser.add_argument("--all", action="store_true", help="пересчитать всем трекам")
    args = parser.parse_args()
    asyncio.run(_reindex(args.all))


if __name__ == "__main__":
    main()

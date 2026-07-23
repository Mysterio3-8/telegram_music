"""Жанры каталога.

  python -m app.cli.genres seed   # идемпотентный сид дерева жанров
  python -m app.cli.genres stats  # сколько жанров и привязок в базе
"""
import argparse
import asyncio

from sqlalchemy import func, select

from app.db.base import session_factory
from app.db.models import ArtistGenre, Genre
from app.services.genres import seed_genres


async def _seed() -> None:
    async with session_factory() as session:
        created, existed = await seed_genres(session)
    print(f"Жанров создано: {created}, уже были: {existed}")


async def _stats() -> None:
    async with session_factory() as session:
        genres = (await session.scalar(select(func.count()).select_from(Genre))) or 0
        links = (await session.scalar(select(func.count()).select_from(ArtistGenre))) or 0
    print(f"Жанров: {genres}, привязок артист↔жанр: {links}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Жанры: сид и статистика")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("seed")
    sub.add_parser("stats")

    args = parser.parse_args()
    if args.command == "seed":
        asyncio.run(_seed())
    else:
        asyncio.run(_stats())


if __name__ == "__main__":
    main()

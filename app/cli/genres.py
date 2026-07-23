"""Жанры каталога.

  python -m app.cli.genres seed            # идемпотентный сид дерева жанров
  python -m app.cli.genres make-playlists  # подборки «редакции» по жанрам (от первого админа)
  python -m app.cli.genres stats           # сколько жанров и привязок в базе
"""
import argparse
import asyncio

from sqlalchemy import func, select

from app.config import settings
from app.db.base import session_factory
from app.db.models import ArtistGenre, Genre, User
from app.services.genre_playlists import generate_genre_playlists
from app.services.genres import seed_genres


async def _seed() -> None:
    async with session_factory() as session:
        created, existed = await seed_genres(session)
    print(f"Жанров создано: {created}, уже были: {existed}")


async def _make_playlists(telegram_id: int | None) -> None:
    """Кураторские подборки = плейлисты админа (раздел «Кураторы» Mini App)."""
    admin_tid = telegram_id or min(settings.admin_id_set, default=0)
    if not admin_tid:
        print("Не задан админ: укажите --user <telegram_id> или ADMIN_IDS в .env")
        return
    async with session_factory() as session:
        user = await session.scalar(select(User).where(User.telegram_id == admin_tid))
        if user is None:
            print(f"Пользователь {admin_tid} не найден — он должен хоть раз зайти в бота")
            return
        results = await generate_genre_playlists(session, user.id)
    for item in results:
        marker = "создан" if item.created else "обновлён"
        print(f"{marker}: {item.title} — {item.track_count} треков")
    print(f"Подборок всего: {len(results)}")


async def _stats() -> None:
    async with session_factory() as session:
        genres = (await session.scalar(select(func.count()).select_from(Genre))) or 0
        links = (await session.scalar(select(func.count()).select_from(ArtistGenre))) or 0
    print(f"Жанров: {genres}, привязок артист↔жанр: {links}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Жанры: сид и статистика")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("seed")
    playlists = sub.add_parser("make-playlists")
    playlists.add_argument("--user", type=int, default=None, help="telegram_id админа-«редакции»")
    sub.add_parser("stats")

    args = parser.parse_args()
    if args.command == "seed":
        asyncio.run(_seed())
    elif args.command == "make-playlists":
        asyncio.run(_make_playlists(args.user))
    else:
        asyncio.run(_stats())


if __name__ == "__main__":
    main()

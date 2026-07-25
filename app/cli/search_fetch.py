"""Поисковый парсер #2 — живой прогон из консоли (проверка блока C).

  python -m app.cli.search_fetch "kizaru фейк айди"           # только поиск+скачивание
  python -m app.cli.search_fetch "элджей розовое вино" --user 5852263277  # + минт в чат

Без --user печатает, что нашёл (не минтит). С --user — заводит трек и кладёт
пользователю в библиотеку (нужен BOT_TOKEN).
"""
import argparse
import asyncio

from aiogram import Bot

from app.config import settings
from app.db.base import session_factory
from app.services.track_lookup import find_track
from app.services.track_lookup.importer import import_by_query
from app.services.youtube.user_import import UserImportRejected


async def _dry(query: str) -> None:
    found = find_track(query)  # ранжирование: транслит/опечатки/по 1 слову
    if found is None:
        print(f"Не нашли: {query}")
        return
    print(f"Найдено [{found.source}]: {found.title}"
          f"{f' — {found.artist}' if found.artist else ''} | {found.url}")


async def _fetch(query: str, telegram_id: int) -> None:
    bot = Bot(token=settings.bot_token)
    try:
        async with session_factory() as session:
            try:
                track, created = await import_by_query(session, bot, query, telegram_id)
            except UserImportRejected as exc:
                print(f"Не удалось: {exc}")
                return
    finally:
        await bot.session.close()
    print(f"{'Создан' if created else 'Уже был'}: {track.artist} — {track.title} (id={track.id})")


def main() -> None:
    parser = argparse.ArgumentParser(description="Поисковый парсер: найти трек отовсюду")
    parser.add_argument("query")
    parser.add_argument("--user", type=int, default=None, help="telegram_id — минт в библиотеку")
    args = parser.parse_args()
    if args.user:
        asyncio.run(_fetch(args.query, args.user))
    else:
        asyncio.run(_dry(args.query))


if __name__ == "__main__":
    main()

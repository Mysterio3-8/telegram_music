"""Чистка каталога под живой поиск (решение владельца 2026-08-02).

По умолчанию НИЧЕГО не удаляет — только показывает, сколько чего попадёт под нож.
Удаление необратимо и задевает библиотеки живых пользователей, поэтому включается
явным --apply.

    python -m app.cli.cleanup_catalog                 # посмотреть числа
    python -m app.cli.cleanup_catalog --apply         # удалить шлак
    python -m app.cli.cleanup_catalog --apply --fingerprints  # и стереть отпечатки
"""
import argparse
import asyncio

from app.db.base import session_factory
from app.services.catalog_cleanup import (
    count_stale_tracks,
    delete_stale_tracks,
    drop_fingerprints,
)
from app.storage import get_storage


async def main() -> None:
    parser = argparse.ArgumentParser(description="Чистка каталога под живой поиск")
    parser.add_argument("--apply", action="store_true", help="действительно удалить")
    parser.add_argument(
        "--fingerprints",
        action="store_true",
        help="стереть отпечатки (освобождает индекс на 128 МБ)",
    )
    args = parser.parse_args()

    async with session_factory() as session:
        stats = await count_stale_tracks(session)
        print(
            f"Клипы: {stats['clips']}\n"
            f"Длиннее 15 минут: {stats['too_long']}\n"
            f"Без обложки: {stats['no_cover']}\n"
            f"Под удаление всего (с пересечениями): {stats['total']}"
        )
        if not args.apply:
            print("\nЭто предпросмотр. Удалить — повторить с --apply")
            return

        deleted = await delete_stale_tracks(session, get_storage())
        print(f"Удалено треков: {deleted}")
        if args.fingerprints:
            cleared = await drop_fingerprints(session)
            print(f"Отпечатков стёрто: {cleared} (индекс освободится после VACUUM)")


if __name__ == "__main__":
    asyncio.run(main())

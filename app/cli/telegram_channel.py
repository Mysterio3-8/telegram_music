"""Управление импортом из личного Telegram-канала.

    python -m app.cli.telegram_channel add <channel> [--title NAME]  — добавить источник
    python -m app.cli.telegram_channel list                          — источники и их статус
    python -m app.cli.telegram_channel scan <source_id|all>          — сканировать и заполнить очередь
    python -m app.cli.telegram_channel scan-due                      — сканировать просроченные
    python -m app.cli.telegram_channel recover                       — вернуть оборванные задачи

Перед первым использованием: `python -m app.cli.telegram_login` (см. этот файл).
"""
import argparse
import asyncio
import logging

from app.db.base import session_factory
from app.services.telegram_channel.sources import add_source, list_sources
from app.tasks.telegram_channel import (
    telegram_channel_recover,
    telegram_channel_scan_due,
    telegram_channel_scan_source,
)

logger = logging.getLogger("telegram-channel-cli")


async def _add(channel: str, title: str | None) -> None:
    async with session_factory() as session:
        source = await add_source(session, channel, title)
    logger.info("Источник добавлен: id=%s %s", source.id, source.channel)
    telegram_channel_scan_source.delay(source_id=source.id)
    logger.info("Первичный импорт запущен в фоне (воркер tg-music-telegram-channel)")


async def _list() -> None:
    async with session_factory() as session:
        sources = await list_sources(session)
    if not sources:
        logger.info("Источников нет")
        return
    for s in sources:
        logger.info(
            "id=%s [%s] найдено=%s импортировано=%s проверка=%s %s",
            s.id, s.status, s.found_count, s.imported_count, s.last_checked_at, s.channel,
        )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Импорт из личного Telegram-канала")
    sub = parser.add_subparsers(dest="command", required=True)

    p_add = sub.add_parser("add", help="Добавить источник и запустить импорт")
    p_add.add_argument("channel", help="@username, invite-ссылка или id канала")
    p_add.add_argument("--title", default=None, help="Имя канала (fallback-исполнитель)")

    sub.add_parser("list", help="Показать источники")

    p_scan = sub.add_parser("scan", help="Сканировать источник")
    p_scan.add_argument("source", help="ID источника или 'all'")

    sub.add_parser("scan-due", help="Сканировать просроченные источники")
    sub.add_parser("recover", help="Вернуть оборванные задачи в очередь")

    args = parser.parse_args()

    if args.command == "add":
        asyncio.run(_add(args.channel, args.title))
    elif args.command == "list":
        asyncio.run(_list())
    elif args.command == "scan":
        if args.source == "all":
            telegram_channel_scan_due.delay()
            logger.info("Сканирование всех активных источников запущено в фоне")
        else:
            telegram_channel_scan_source.delay(source_id=int(args.source))
            logger.info("Сканирование источника %s запущено в фоне", args.source)
    elif args.command == "scan-due":
        telegram_channel_scan_due.delay()
        logger.info("Проверка просроченных источников запущена в фоне")
    elif args.command == "recover":
        telegram_channel_recover.delay()
        logger.info("Восстановление очереди запущено в фоне")


if __name__ == "__main__":
    main()

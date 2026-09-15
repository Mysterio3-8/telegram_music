"""Ежедневные напоминания «продлите Premium бесплатно» (app/services/reminders.py).

    python -m app.cli.reminders          # отправить
    python -m app.cli.reminders --dry    # только посчитать, никому не писать

Запускается ежедневным таймером (deploy/tg-music-catalog-maintain) после автопродления.
"""
import argparse
import asyncio

from app.db.base import session_factory
from app.services.bot_api import BotApi
from app.services.reminders import send_due_reminders


async def _run(dry: bool) -> None:
    async with session_factory() as session, BotApi() as bot:
        report = await send_due_reminders(session, bot, dry=dry)
    mode = "проверка (никому не писали)" if dry else "отправка"
    print(
        f"Напоминания, {mode}: к отправке {report.due} {report.by_kind}, "
        f"ушло {report.sent}, заблокировали бота {report.blocked}, сбоев {report.failed}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry", action="store_true")
    asyncio.run(_run(parser.parse_args().dry))


if __name__ == "__main__":
    main()

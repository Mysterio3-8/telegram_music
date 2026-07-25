"""Ежедневное автопродление Premium (блок E): списывает 49 ₽ с сохранённых
способов у подписок, истекающих в ближайшие сутки.

  python -m app.cli.autorenew

Запускается ежедневным таймером (deploy/tg-music-catalog-maintain). Мастер-выключатель
— settings.premium_autorenew. Списывает только тех, кто платил с согласием на
автопродление (сохранённый payment_method) и не выключил его в настройках.
"""
import asyncio

from app.db.base import session_factory
from app.services.yookassa_payments import charge_due_subscriptions


async def _run() -> None:
    async with session_factory() as session:
        charged = await charge_due_subscriptions(session)
    print(f"Автопродление: продлено подписок — {charged}")


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()

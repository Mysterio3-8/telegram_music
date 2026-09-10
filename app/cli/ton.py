"""TON-донаты из командной строки: проверка настроек и разбор приходов.

    python -m app.cli.ton check          # разобрать свежие приходы и зачесть
    python -m app.cli.ton probe          # проверить токен Crypto Pay
    python -m app.cli.ton memo <tg_id>   # показать метку платежа для человека

`check` вызывается таймером `tg-music-ton-check` каждые две минуты. Он нужен
только прямому переводу на кошелёк: у Crypto Pay есть вебхук, и там ждать
таймера незачем.
"""
import argparse
import asyncio
import sys

from app.config import settings
from app.db.base import session_factory
from app.services import crypto_pay, ton_donations


async def cmd_check() -> int:
    if not ton_donations.is_configured():
        print(
            "Прямой приём TON не настроен: нужны TON_WALLET_ADDRESS и TON_RUB_PER_TON в .env"
        )
        return 1
    async with session_factory() as session:
        counted = await ton_donations.collect(session)
    # Молчим, когда ничего нового: таймер ходит каждые две минуты, и болтливый
    # вывод забил бы журнал полностью бесполезными строками.
    if counted:
        print(f"Зачтено новых донатов: {counted}")
    return 0


async def cmd_probe() -> int:
    print("Crypto Pay:")
    if not crypto_pay.is_configured():
        print("  токен не задан (CRYPTO_PAY_TOKEN) — способ выключен")
    else:
        me = await crypto_pay.get_me()
        if me is None:
            print("  🔴 токен задан, но API его не принял — подробности в журнале")
            return 1
        print(f"  ✅ приложение: {me.get('name')} (id {me.get('app_id')})")

    print("\nПрямой перевод на кошелёк:")
    if not ton_donations.is_configured():
        print("  не настроен (нужны TON_WALLET_ADDRESS и TON_RUB_PER_TON)")
        return 0
    print(f"  адрес: {settings.ton_wallet_address}")
    print(f"  курс:  {settings.ton_rub_per_ton} ₽ за 1 TON")
    transactions = await ton_donations.fetch_incoming(limit=5)
    if transactions is None:
        print("  🔴 блокчейн не отвечает")
        return 1
    print(f"  ✅ блокчейн отвечает, последних транзакций: {len(transactions)}")
    return 0


async def cmd_memo(args: argparse.Namespace) -> int:
    print(ton_donations.make_memo(args.telegram_id, anonymous=args.anonymous))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="TON-донаты")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="разобрать свежие приходы на кошелёк")
    sub.add_parser("probe", help="проверить настройки обоих способов")
    memo = sub.add_parser("memo", help="показать метку платежа")
    memo.add_argument("telegram_id", type=int)
    memo.add_argument("--anonymous", action="store_true")

    args = parser.parse_args()
    if args.command == "check":
        return asyncio.run(cmd_check())
    if args.command == "probe":
        return asyncio.run(cmd_probe())
    if args.command == "memo":
        return asyncio.run(cmd_memo(args))
    return 1


if __name__ == "__main__":
    sys.exit(main())

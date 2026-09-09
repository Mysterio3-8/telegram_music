"""Проба Wallet Pay: подтвердить контракт с живым API до того, как им платят люди.

    python -m app.cli.walletpay probe --amount 10
    python -m app.cli.walletpay status <external_id или их id>

Зачем это отдельной командой. Формат запросов Wallet Pay в коде взят из общего
знания об этом API, а не подтверждён документацией — она рендерится скриптом и
из окружения разработки недоступна. Выкатить непроверенную интеграцию, через
которую пойдут чужие деньги, нельзя, поэтому:

1. проба создаёт НАСТОЯЩИЙ заказ на минимальную сумму и печатает ответ целиком;
2. видно, принял ли API наши поля и вернул ли ссылку на оплату;
3. только после этого в .env ставится WALLET_PAY_VERIFIED=true, и кнопка «TON»
   появляется у людей.

⚠️ Заказ создаётся реальный. Платить по ссылке необязательно — он протухнет сам
через три часа. Но если оплатить, проба заодно проверит и путь уведомления.
"""
import argparse
import asyncio
import json
import sys

from app.config import settings
from app.services import wallet_pay


def _print_settings() -> bool:
    print("Настройки:")
    print(f"  ключ магазина задан: {'да' if settings.wallet_pay_api_key else 'НЕТ'}")
    print(f"  курс TON→₽:          {settings.ton_rub_per_ton or 'НЕ ЗАДАН'}")
    print(f"  предохранитель снят: {'да' if settings.wallet_pay_verified else 'нет'}")
    if not settings.wallet_pay_api_key:
        print("\nНечего проверять: впишите WALLET_PAY_API_KEY в .env на сервере.")
        return False
    if settings.ton_rub_per_ton <= 0:
        print(
            "\nНечего проверять: впишите TON_RUB_PER_TON в .env — без курса "
            "нечем перевести рубли в TON."
        )
        return False
    return True


async def cmd_probe(args: argparse.Namespace) -> int:
    if not _print_settings():
        return 1

    amount = args.amount
    print(f"\nСоздаю заказ на {amount} ₽ = {wallet_pay.ton_for_rub(amount)} TON…")
    result = await wallet_pay.create_order(args.user, amount, force=True)
    if result is None:
        print(
            "\n🔴 Заказ не создан. Причина — в выводе выше или в журнале.\n"
            "Что бывает: ключ не тот, магазин не активирован, либо ответ API "
            "другой формы, чем ждёт код. Пришлите этот вывод — поправлю поля."
        )
        return 1

    external_id, link = result
    print("\n✅ Заказ создан, API принял наши поля.")
    print(f"  наш id:     {external_id}")
    print(f"  ссылка:     {link}")
    print(
        "\nЧто дальше:\n"
        "1. Откройте ссылку и убедитесь, что сумма и описание верные.\n"
        "2. Впишите в .env на сервере: WALLET_PAY_VERIFIED=true\n"
        "3. Перезапустите бота и API — кнопка «Поддержать в TON» появится.\n"
        "\nЕсли оплатите заказ, проверьте, что донат зачтён: "
        "python -m app.cli.goals list"
    )
    return 0


async def cmd_status(args: argparse.Namespace) -> int:
    if not _print_settings():
        return 1
    body = await wallet_pay.get_order_status(args.order_id)
    if body is None:
        print("Не удалось получить статус — подробности в журнале.")
        return 1
    print(json.dumps(body, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Проверка интеграции с Wallet Pay")
    sub = parser.add_subparsers(dest="command", required=True)

    probe = sub.add_parser("probe", help="создать пробный заказ и проверить контракт")
    probe.add_argument("--amount", type=int, default=10, help="сумма в рублях (по умолчанию 10)")
    probe.add_argument(
        "--user",
        type=int,
        default=settings.first_admin_id or 0,
        help="telegram_id покупателя (по умолчанию первый админ)",
    )

    status = sub.add_parser("status", help="показать состояние заказа")
    status.add_argument("order_id")

    args = parser.parse_args()
    if args.command == "probe":
        return asyncio.run(cmd_probe(args))
    if args.command == "status":
        return asyncio.run(cmd_status(args))
    return 1


if __name__ == "__main__":
    sys.exit(main())

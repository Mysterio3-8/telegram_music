"""Одноразовый интерактивный вход в личный Telegram-аккаунт (Telethon).

Нужен один раз, чтобы прочитать историю канала — Bot API не даёт боту доступ
к постам, отправленным до его добавления. Дальше сохранённая сессия
используется фоновыми задачами без диалога.

Запуск (только в интерактивном терминале, не из Celery):
    python -m app.cli.telegram_login

Спросит номер телефона и код из Telegram/SMS (при включённой 2FA — пароль).
Файл сессии (TELEGRAM_SESSION_PATH) даёт полный доступ к аккаунту, как и сам
номер телефона: держите вне git, права 600, не передавайте никому.
"""
import asyncio
import logging

from telethon import TelegramClient

from app.config import settings

logging.basicConfig(level=logging.WARNING)


async def main() -> None:
    if not settings.telegram_api_id or not settings.telegram_api_hash:
        raise SystemExit(
            "Задайте TELEGRAM_API_ID и TELEGRAM_API_HASH в .env "
            "(получить на https://my.telegram.org → API development tools)"
        )

    client = TelegramClient(
        settings.telegram_session_path, settings.telegram_api_id, settings.telegram_api_hash
    )
    await client.start()  # интерактивно спросит номер телефона и код
    me = await client.get_me()
    print(f"Успешный вход: {me.first_name} (id={me.id}).")
    print(f"Сессия сохранена в {settings.telegram_session_path} — дальше вход не нужен.")
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())

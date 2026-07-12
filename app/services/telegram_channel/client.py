"""MTProto-клиент (Telethon) от лица личного аккаунта — единственный способ прочитать
историю канала: Bot API не даёт боту доступ к сообщениям, отправленным до его
добавления. Сессия создаётся один раз через `python -m app.cli.telegram_login`
и переиспользуется здесь без диалога."""
from telethon import TelegramClient

from app.config import settings


def build_client() -> TelegramClient:
    return TelegramClient(
        settings.telegram_session_path, settings.telegram_api_id, settings.telegram_api_hash
    )


def is_configured() -> bool:
    return bool(settings.telegram_api_id and settings.telegram_api_hash)

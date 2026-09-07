"""MTProto-клиент (Telethon) от лица личного аккаунта — единственный способ прочитать
историю канала: Bot API не даёт боту доступ к сообщениям, отправленным до его
добавления. Сессия создаётся один раз через `python -m app.cli.telegram_login`
и переиспользуется здесь без диалога."""
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # только для аннотаций, в рантайме не выполняется
    from telethon import TelegramClient

# ⚠️ Импорт намеренно мягкий. Подсистема чтения ТГ-канала опциональна: каждый её
# вызов и так закрыт проверкой is_configured(), а админский экран показывает
# предупреждение, когда вход не настроен. Но сам импорт был жёстким — и это
# делало НЕобязательную библиотеку обязательной для запуска: модуль тянется из
# app/main.py (роутер admin_telegram_channel) и из app/tasks/celery_app.py, то
# есть сломанный или не доехавший telethon уронил бы бота и ВСЕ воркеры на
# старте, до того как появится хоть один обработчик ошибок. Это ровно тот
# сценарий, от которого защищают graceful-фолбэки на границах Redis/Celery/fpcalc.
try:
    from telethon import TelegramClient as _TelegramClient
except ModuleNotFoundError:  # библиотека не установлена — живём без импорта канала
    _TelegramClient = None

from app.config import settings


def build_client() -> "TelegramClient":
    if _TelegramClient is None:
        raise RuntimeError(
            "telethon не установлен — импорт из ТГ-канала недоступен. "
            "Поставить: pip install -r requirements.txt"
        )
    return _TelegramClient(
        settings.telegram_session_path, settings.telegram_api_id, settings.telegram_api_hash
    )


def is_configured() -> bool:
    # Без библиотеки подсистема нерабочая — отвечаем честно «не настроена»,
    # чтобы вызывающий код пошёл по своей обычной ветке отказа, а не по исключению.
    if _TelegramClient is None:
        return False
    return bool(settings.telegram_api_id and settings.telegram_api_hash)

"""Постановка задач Celery из процесса API — без импорта самих задач.

`app.tasks.celery_app` регистрирует ВСЕ задачи, а модули задач тянут aiogram,
yt-dlp и импортёры. Процессу API всё это не нужно: он только кладёт сообщение
в брокер, исполняет воркер. Поэтому здесь отдельный лёгкий клиент и
`send_task` по имени.

⚠️ Очередь указывается явно: у `send_task` нет доступа к `queue=` из декоратора
задачи. Соответствие имён и очередей воркеру стережёт
tests/test_api_process_imports.py — переименуешь задачу или сменишь очередь,
тест упадёт раньше, чем задача молча уйдёт в очередь, которую никто не разбирает.
"""
from celery import Celery

from app.config import settings

QUEUES: dict[str, str] = {
    "search.fetch": "youtube_user",
    "search.fetch_candidate": "youtube_user",
    "search.repair_track": "youtube_user",
    "transfer.playlist": "celery",
}

_client: Celery | None = None


def _app() -> Celery:
    global _client
    if _client is None:
        _client = Celery("tgmusic-api", broker=settings.effective_celery_broker or None)
        _client.conf.update(
            task_serializer="json",
            accept_content=["json"],
            task_ignore_result=True,
        )
    return _client


def enqueue(name: str, *args, **kwargs) -> None:
    """Кладёт задачу в брокер. Брокер недоступен — исключение, решает вызывающий."""
    _app().send_task(name, args=args, kwargs=kwargs, queue=QUEUES[name])

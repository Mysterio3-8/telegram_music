from celery import Celery

from app.config import settings

celery_app = Celery("tgmusic", broker=settings.effective_celery_broker or None)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    task_ignore_result=True,
    broker_connection_retry_on_startup=True,
    # Фоновые задачи — каждая группа в свою очередь (свой воркер с лимитом параллельности)
    task_routes={
        "youtube.*": {"queue": "youtube"},
        "telegram_channel.*": {"queue": "telegram_channel"},
    },
)

# Регистрируем задачи в воркере (celery -A app.tasks.celery_app worker)
from app.tasks import enrich, telegram_channel, youtube  # noqa: E402,F401

from celery import Celery

from app.config import settings

celery_app = Celery("tgmusic", broker=settings.effective_celery_broker or None)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    task_ignore_result=True,
    broker_connection_retry_on_startup=True,
    # YouTube-задачи — в отдельную очередь (свой воркер с лимитом параллельности, §14)
    task_routes={"youtube.*": {"queue": "youtube"}},
)

# Регистрируем задачи в воркере (celery -A app.tasks.celery_app worker)
from app.tasks import enrich, youtube  # noqa: E402,F401

from celery import Celery

from app.config import settings

celery_app = Celery("tgmusic", broker=settings.effective_celery_broker or None)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    task_ignore_result=True,
    broker_connection_retry_on_startup=True,
    # Фоновые задачи — каждая группа в свою очередь (свой воркер с лимитом параллельности).
    # soundcloud.* — отдельно от youtube.*: иначе новый SoundCloud-источник стоит в хвосте
    # многосотенного бэклога поштучных YouTube-импортов и выглядит «зависшим».
    # youtube.user_import (точное совпадение проверяется ДО wildcard youtube.*) — ссылка,
    # которую сам пользователь кинул боту, должна обработаться быстро, а не ждать
    # своей очереди за массовым сканом чьего-то канала на сотни видео.
    # Порядок важен: точные имена задач до wildcard. Ссылки от пользователей
    # (youtube.user_import, soundcloud.user_import) — в отзывчивую очередь youtube_user,
    # чтобы не стоять за бэклогом массовых сканов каналов/профилей.
    task_routes={
        "soundcloud.user_import": {"queue": "youtube_user"},
        "soundcloud.*": {"queue": "soundcloud"},
        "youtube.user_import": {"queue": "youtube_user"},
        "youtube.*": {"queue": "youtube"},
        "telegram_channel.*": {"queue": "telegram_channel"},
    },
)

# Регистрируем задачи в воркере (celery -A app.tasks.celery_app worker)
from app.tasks import enrich, soundcloud, telegram_channel, youtube  # noqa: E402,F401

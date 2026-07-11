import logging

from app.config import settings

logger = logging.getLogger(__name__)


def enqueue_enrich(track_id: int, file_id: str) -> None:
    """Ставит фоновую задачу обогащения. Без брокера — тихо пропускает (трек уже работает)."""
    if not settings.effective_celery_broker:
        return
    try:
        from app.tasks.enrich import enrich_track

        enrich_track.delay(track_id, file_id)
    except Exception as exc:  # брокер недоступен — не ломаем загрузку
        logger.warning("Не удалось поставить задачу обогащения track=%s: %s", track_id, exc)

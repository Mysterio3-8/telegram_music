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


def enqueue_user_import(
    video_id: str, telegram_id: int, chat_id: int, quiet: bool = False
) -> bool:
    """Импорт по ссылке от пользователя. False — очередь недоступна, сказать пользователю."""
    if not settings.effective_celery_broker:
        return False
    try:
        from app.tasks.youtube import youtube_user_import

        youtube_user_import.delay(
            video_id=video_id, telegram_id=telegram_id, chat_id=chat_id, quiet=quiet
        )
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("Не удалось поставить user-импорт video=%s: %s", video_id, exc)
        return False


def enqueue_soundcloud_user_import(
    url: str, telegram_id: int, chat_id: int, quiet: bool = False
) -> bool:
    """Импорт трека SoundCloud по ссылке от пользователя. False — очередь недоступна."""
    if not settings.effective_celery_broker:
        return False
    try:
        from app.tasks.soundcloud import soundcloud_user_import

        soundcloud_user_import.delay(
            url=url, telegram_id=telegram_id, chat_id=chat_id, quiet=quiet
        )
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("Не удалось поставить SoundCloud user-импорт %s: %s", url, exc)
        return False

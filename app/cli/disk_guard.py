"""Сторож диска из терминала: python -m app.cli.disk_guard

Запускается ежедневным таймером обслуживания. Освобождает место, если свободного
меньше disk_reclaim_free_mb, и предупреждает админа в бот, если после чистки его
всё равно меньше disk_alert_free_mb.
"""
import asyncio
import logging

from app.config import settings
from app.services.disk_guard import alert_text, reclaim_disk
from app.services.telegram_send import send_message

logger = logging.getLogger(__name__)


async def _notify_admin(text: str) -> None:
    chat_id = settings.first_admin_id
    if chat_id is None:
        logger.warning("ADMIN_IDS пуст — предупреждение о диске отправить некому:\n%s", text)
        return
    await send_message(chat_id, text)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    report = reclaim_disk()
    print(
        f"Свободно: было {report.free_before_mb} МБ, стало {report.free_after_mb} МБ "
        f"(кэш: {report.removed_cache_files} файлов, бэкапы: {report.removed_backups})"
    )

    text = alert_text(report)
    if text:
        asyncio.run(_notify_admin(text))


if __name__ == "__main__":
    main()

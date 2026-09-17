"""Резервная копия БД из терминала (блок G): python -m app.cli.backup

Запускается ежедневным таймером (deploy/tg-music-backup). Делает консистентный
снимок БД в backup_dir и оставляет последние backup_keep копий."""
import asyncio

from app.services.backup import _sqlite_path, create_backup
from app.services.backup_offsite import upload_backup
from app.services.backup_telegram import send_to_owner


def _alert(text: str) -> None:
    """Тревога владельцу. Сбой отправки не роняет таймер: снимок уже сделан."""
    from app.config import settings
    from app.services.telegram_send import send_message

    chat_id = settings.health_alert_id
    if chat_id is None:
        return
    try:
        asyncio.run(send_message(chat_id, text))
    except Exception:  # noqa: BLE001
        print("Тревогу отправить не удалось")


def main() -> None:
    path = create_backup()
    print(f"Бэкап готов: {path}")

    # Проверка восстановления (17.09): снимок, который не открывали, — надежда, а не бэкап
    from app.services.backup_verify import verify_sqlite_backup

    verdict = verify_sqlite_backup(path, _sqlite_path())
    print(verdict.summary())
    if not verdict.ok:
        _alert(f"🚨 {verdict.summary()}")

    offsite = upload_backup(path)
    if offsite.uploaded_key:
        print(f"Выгружен в облако: {offsite.uploaded_key} (удалено старых: {offsite.removed_remote})")
    elif offsite.error:
        print(f"Выгрузка в облако не удалась: {offsite.error}")

    # Копия вне сервера через Telegram (16.09): S3-ключей нет, а бот есть всегда
    print(asyncio.run(send_to_owner(path)))


if __name__ == "__main__":
    main()

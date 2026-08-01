"""Резервная копия БД из терминала (блок G): python -m app.cli.backup

Запускается ежедневным таймером (deploy/tg-music-backup). Делает консистентный
снимок БД в backup_dir и оставляет последние backup_keep копий."""
from app.services.backup import create_backup
from app.services.backup_offsite import upload_backup


def main() -> None:
    path = create_backup()
    print(f"Бэкап готов: {path}")

    offsite = upload_backup(path)
    if offsite.uploaded_key:
        print(f"Выгружен в облако: {offsite.uploaded_key} (удалено старых: {offsite.removed_remote})")
    elif offsite.error:
        print(f"Выгрузка в облако не удалась: {offsite.error}")


if __name__ == "__main__":
    main()

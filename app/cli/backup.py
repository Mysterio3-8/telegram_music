"""Резервная копия БД из терминала (блок G): python -m app.cli.backup

Запускается ежедневным таймером (deploy/tg-music-backup). Делает консистентный
снимок БД в backup_dir и оставляет последние backup_keep копий."""
from app.services.backup import create_backup


def main() -> None:
    path = create_backup()
    print(f"Бэкап готов: {path}")


if __name__ == "__main__":
    main()

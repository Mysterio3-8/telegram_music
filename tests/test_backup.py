import sqlite3
from pathlib import Path

from app.config import settings
from app.services.backup import create_backup


def test_create_backup_makes_snapshot_and_prunes(tmp_path, monkeypatch):
    # рабочая БД SQLite во временном каталоге
    db_path = tmp_path / "work.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
    conn.execute("INSERT INTO t (v) VALUES ('hello')")
    conn.commit()
    conn.close()

    backup_dir = tmp_path / "backups"
    monkeypatch.setattr(settings, "database_url", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setattr(settings, "backup_dir", str(backup_dir))
    monkeypatch.setattr(settings, "backup_keep", 2)

    made = []
    for _ in range(3):
        # разные имена по времени — подменять не нужно, метка до секунды; форсируем уникальность
        path = create_backup()
        made.append(path)
        # сдвигаем mtime, чтобы ротация была детерминированной
        import os
        import time

        os.utime(path, (time.time() + len(made), time.time() + len(made)))

    backups = list(Path(backup_dir).glob("db-*.sqlite"))
    assert len(backups) <= 2  # ротация оставила не больше backup_keep

    # снимок читается и содержит данные
    newest = max(backups, key=lambda p: p.stat().st_mtime)
    check = sqlite3.connect(newest)
    assert check.execute("SELECT v FROM t").fetchone()[0] == "hello"
    check.close()

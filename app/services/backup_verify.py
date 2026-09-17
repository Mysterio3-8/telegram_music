"""Проверка, что свежий снимок базы можно восстановить (17.09).

Бэкап, который ни разу не открывали, — это надежда, а не бэкап. 16.09 восстановление
проверили руками впервые (docs/БЭКАП.md); теперь то же самое делает ночной таймер
после каждого снимка, и при сбое пишет владельцу.

Что проверяется — на ВРЕМЕННОЙ копии, сам снимок не трогаем:
- `PRAGMA integrity_check` = ok — файл не битый;
- миграция в снимке = миграция живой базы — снимок той же схемы, что и код;
- люди и треки есть, и их не стало резко меньше, чем в живой базе. Снимок, в котором
  вдруг пусто или вдвое меньше людей, формально целый, но восстанавливать его — беда.

PostgreSQL (`.dump`) пока не проверяется: прод на SQLite, pg_restore в пустую базу —
отдельная история, когда до переезда дойдёт.
"""
from __future__ import annotations

import shutil
import sqlite3
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

# Снимок меньше этой доли живой базы по людям/трекам — подозрительный.
# Между снимком (04:00) и проверкой проходят секунды, так что расхождение должно быть ~0;
# 0.9 оставляет запас на случай, если проверку запустят руками спустя время.
MIN_SHARE = 0.9
_TABLES = ("users", "tracks")


@dataclass
class VerifyResult:
    snapshot: str
    problems: list[str] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)
    migration: str | None = None

    @property
    def ok(self) -> bool:
        return not self.problems

    def summary(self) -> str:
        if not self.ok:
            return f"Бэкап {self.snapshot} НЕ прошёл проверку: " + "; ".join(self.problems)
        counts = ", ".join(f"{name} {value}" for name, value in self.counts.items())
        return f"Бэкап {self.snapshot} проверен: целостность ok, миграция {self.migration}, {counts}"


def _read(connection: sqlite3.Connection) -> tuple[str | None, dict[str, int]]:
    try:
        migration = connection.execute("select version_num from alembic_version").fetchone()
        migration = migration[0] if migration else None
    except sqlite3.DatabaseError:
        migration = None
    counts = {}
    for table in _TABLES:
        try:
            counts[table] = connection.execute(f"select count(*) from {table}").fetchone()[0]  # noqa: S608 — имена из константы
        except sqlite3.DatabaseError:
            counts[table] = -1
    return migration, counts


def verify_sqlite_backup(snapshot: Path, live_path: str | None) -> VerifyResult:
    result = VerifyResult(snapshot=snapshot.name)
    if snapshot.suffix != ".sqlite":
        return result  # .dump PostgreSQL — см. docstring
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "check.sqlite"
        shutil.copyfile(snapshot, copy)
        try:
            connection = sqlite3.connect(copy)
        except sqlite3.DatabaseError as error:
            result.problems.append(f"не открывается: {error}")
            return result
        try:
            try:
                integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
            except sqlite3.DatabaseError as error:
                result.problems.append(f"файл повреждён: {error}")
                return result
            if integrity != "ok":
                result.problems.append(f"integrity_check: {integrity}")
            result.migration, result.counts = _read(connection)
        finally:
            connection.close()

    if result.migration is None:
        result.problems.append("нет версии миграции — это не база приложения")
    for table, value in result.counts.items():
        if value < 0:
            result.problems.append(f"нет таблицы {table}")
        elif value == 0:
            result.problems.append(f"таблица {table} пустая")

    if live_path and Path(live_path).exists():
        # Живую базу — только на чтение: проверка не должна брать её блокировку записи
        live = sqlite3.connect(f"file:{live_path}?mode=ro", uri=True)
        try:
            live_migration, live_counts = _read(live)
        finally:
            live.close()
        if live_migration and result.migration and live_migration != result.migration:
            result.problems.append(f"миграция снимка {result.migration} ≠ живой базы {live_migration}")
        for table, live_value in live_counts.items():
            value = result.counts.get(table, 0)
            if live_value > 0 and value >= 0 and value < live_value * MIN_SHARE:
                result.problems.append(f"{table}: в снимке {value}, в живой базе {live_value}")
    return result

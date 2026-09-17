"""Автопроверка восстановления снимка базы после ночного бэкапа (17.09)."""
import sqlite3

from app.services.backup_verify import verify_sqlite_backup


def _db(path, users=10, tracks=20, migration="9c8d7e6f5a4b"):
    con = sqlite3.connect(path)
    con.execute("create table alembic_version (version_num varchar(32))")
    if migration:
        con.execute("insert into alembic_version values (?)", (migration,))
    con.execute("create table users (id integer primary key)")
    con.execute("create table tracks (id integer primary key)")
    con.executemany("insert into users default values", [()] * users)
    con.executemany("insert into tracks default values", [()] * tracks)
    con.commit()
    con.close()
    return path


def test_healthy_snapshot_passes(tmp_path):
    live = _db(tmp_path / "live.db")
    snapshot = _db(tmp_path / "db-20260917-040000.sqlite")
    before = snapshot.read_bytes()
    result = verify_sqlite_backup(snapshot, str(live))
    assert result.ok, result.problems
    assert result.counts == {"users": 10, "tracks": 20} and result.migration == "9c8d7e6f5a4b"
    assert "проверен" in result.summary()
    assert snapshot.read_bytes() == before  # проверка идёт на копии, снимок не тронут


def test_corrupted_file_fails(tmp_path):
    snapshot = tmp_path / "db-x.sqlite"
    snapshot.write_bytes(b"SQLite format 3\x00" + b"\xff" * 4096)
    result = verify_sqlite_backup(snapshot, None)
    assert not result.ok and "НЕ прошёл" in result.summary()


def test_empty_table_and_missing_migration_fail(tmp_path):
    snapshot = _db(tmp_path / "db-x.sqlite", users=0, migration=None)
    problems = " ".join(verify_sqlite_backup(snapshot, None).problems)
    assert "users пустая" in problems and "миграции" in problems


def test_schema_mismatch_with_live_fails(tmp_path):
    live = _db(tmp_path / "live.db", migration="newer")
    snapshot = _db(tmp_path / "db-x.sqlite", migration="older")
    problems = " ".join(verify_sqlite_backup(snapshot, str(live)).problems)
    assert "older" in problems and "newer" in problems


def test_sudden_drop_against_live_fails(tmp_path):
    live = _db(tmp_path / "live.db", users=100)
    snapshot = _db(tmp_path / "db-x.sqlite", users=40)
    problems = " ".join(verify_sqlite_backup(snapshot, str(live)).problems)
    assert "users: в снимке 40, в живой базе 100" in problems


def test_postgres_dump_is_skipped(tmp_path):
    dump = tmp_path / "db-x.dump"
    dump.write_bytes(b"PGDMP")
    assert verify_sqlite_backup(dump, None).ok

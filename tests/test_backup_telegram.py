"""Зашифрованная копия бэкапа владельцу в Telegram (16.09)."""
import shutil
import sqlite3

import pytest

from app.config import settings
from app.services import backup_telegram
from app.services.backup_telegram import OffsiteBackupError, decrypt_backup, encrypt_backup, send_to_owner

needs_openssl = pytest.mark.skipif(shutil.which("openssl") is None, reason="нет openssl")


def _database(path):
    con = sqlite3.connect(path)
    con.execute("create table users (id integer primary key, telegram_id integer)")
    con.executemany("insert into users (telegram_id) values (?)", [(i,) for i in range(500)])
    con.commit()
    con.close()
    return path


@needs_openssl
def test_roundtrip_restores_identical_database(tmp_path):
    source = _database(tmp_path / "db.sqlite")
    encrypted = encrypt_backup(source, tmp_path / "db.enc", "верный-пароль-123")
    blob = encrypted.read_bytes()
    assert not blob.startswith(b"SQLite format 3") and b"telegram_id" not in blob  # не открытым текстом
    assert blob.startswith(b"Salted__")  # формат openssl — расшифровывается без нашего кода

    restored = decrypt_backup(encrypted, tmp_path / "restored.sqlite", "верный-пароль-123")
    assert restored.read_bytes() == source.read_bytes()
    assert not list(tmp_path.glob("*.gz.tmp"))  # промежуточные файлы убраны


@needs_openssl
def test_wrong_password_fails_loudly(tmp_path):
    encrypted = encrypt_backup(_database(tmp_path / "db.sqlite"), tmp_path / "db.enc", "пароль")
    with pytest.raises(OffsiteBackupError):
        decrypt_backup(encrypted, tmp_path / "x.sqlite", "другой")


def test_refuses_without_password(tmp_path):
    with pytest.raises(OffsiteBackupError):
        encrypt_backup(_database(tmp_path / "db.sqlite"), tmp_path / "db.enc", "")


async def test_send_to_owner_disabled_without_password(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "backup_password", "")
    sent = []

    async def fake_send(chat_id, path, caption):
        sent.append(path)
        return True

    monkeypatch.setattr(backup_telegram, "send_document", fake_send)
    result = await send_to_owner(_database(tmp_path / "db.sqlite"))
    assert "BACKUP_PASSWORD" in result and sent == []


@needs_openssl
async def test_send_to_owner_sends_only_encrypted_file(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "backup_password", "секретный-пароль")
    monkeypatch.setattr(type(settings), "health_alert_id", property(lambda self: 12345))
    captured = {}

    async def fake_send(chat_id, path, caption):
        captured.update(chat_id=chat_id, head=path.read_bytes()[:16], name=path.name, caption=caption)
        return True

    monkeypatch.setattr(backup_telegram, "send_document", fake_send)
    result = await send_to_owner(_database(tmp_path / "db.sqlite"))
    assert "отправлена" in result
    assert captured["chat_id"] == 12345
    assert captured["head"].startswith(b"Salted__") and captured["name"].endswith(".enc")
    assert "секретный-пароль" not in captured["caption"]  # пароль в Telegram не уходит


@needs_openssl
async def test_send_failure_is_reported_not_raised(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "backup_password", "пароль")
    monkeypatch.setattr(type(settings), "health_alert_id", property(lambda self: 1))

    async def failing_send(chat_id, path, caption):
        return False

    monkeypatch.setattr(backup_telegram, "send_document", failing_send)
    result = await send_to_owner(_database(tmp_path / "db.sqlite"))
    assert "не отправлена" in result

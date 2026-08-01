"""Offsite-выгрузка бэкапа: не настроена — молчит, упала — не роняет таймер."""
from datetime import datetime, timedelta, timezone

import pytest

from app.config import settings
from app.services import backup_offsite
from app.services.backup_offsite import offsite_enabled, upload_backup


@pytest.fixture
def s3_configured(monkeypatch):
    monkeypatch.setattr(settings, "s3_endpoint_url", "https://s3.example.com")
    monkeypatch.setattr(settings, "s3_access_key", "key")
    monkeypatch.setattr(settings, "s3_secret_key", "secret")
    monkeypatch.setattr(settings, "backup_s3_bucket", "music-backups")
    monkeypatch.setattr(settings, "backup_s3_prefix", "db-backups")


class _FakeClient:
    def __init__(self, existing: list[str] | None = None) -> None:
        self.uploaded: list[tuple[str, str, str]] = []
        self.deleted: list[str] = []
        self._existing = existing or []

    def upload_file(self, path: str, bucket: str, key: str) -> None:
        self.uploaded.append((path, bucket, key))

    def list_objects_v2(self, Bucket: str, Prefix: str) -> dict:  # noqa: N803 — сигнатура boto3
        base = datetime(2026, 8, 1, tzinfo=timezone.utc)
        return {
            "Contents": [
                {"Key": key, "LastModified": base - timedelta(days=index)}
                for index, key in enumerate(self._existing)
            ]
        }

    def delete_object(self, Bucket: str, Key: str) -> None:  # noqa: N803 — сигнатура boto3
        self.deleted.append(Key)


def test_disabled_without_s3_settings(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "s3_endpoint_url", "")
    monkeypatch.setattr(settings, "backup_s3_bucket", "")
    monkeypatch.setattr(settings, "s3_bucket", "")

    assert offsite_enabled() is False
    result = upload_backup(tmp_path / "db-1.sqlite")
    assert result.uploaded_key is None
    assert result.error is None


def test_uploads_backup_under_prefix(s3_configured, monkeypatch, tmp_path):
    client = _FakeClient()
    monkeypatch.setattr(backup_offsite, "_client", lambda: client)
    backup = tmp_path / "db-20260801-040000.sqlite"
    backup.write_bytes(b"snapshot")

    result = upload_backup(backup)

    assert result.uploaded_key == "db-backups/db-20260801-040000.sqlite"
    assert client.uploaded[0][1] == "music-backups"


def test_prunes_old_remote_copies_keeping_newest(s3_configured, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "backup_offsite_keep", 2)
    # Порядок в списке = от свежих к старым (LastModified убывает по индексу)
    client = _FakeClient(existing=["db-3.sqlite", "db-2.sqlite", "db-1.sqlite"])
    monkeypatch.setattr(backup_offsite, "_client", lambda: client)
    backup = tmp_path / "db-4.sqlite"
    backup.write_bytes(b"x")

    result = upload_backup(backup)

    assert result.removed_remote == 1
    assert client.deleted == ["db-1.sqlite"]


def test_network_failure_does_not_raise(s3_configured, monkeypatch, tmp_path):
    def broken_client():
        raise OSError("сеть недоступна")

    monkeypatch.setattr(backup_offsite, "_client", broken_client)
    backup = tmp_path / "db-1.sqlite"
    backup.write_bytes(b"x")

    result = upload_backup(backup)

    assert result.uploaded_key is None
    assert "сеть недоступна" in result.error

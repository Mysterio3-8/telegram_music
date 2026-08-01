"""Выгрузка бэкапа БД за пределы сервера (остаток блока G).

Бэкап, лежащий на том же диске, что и база, защищает ровно от одного сценария —
кривой миграции. От потери сервера он не защищает никак, а на этом боксе он ещё
и съедал 646 МБ из 20 ГБ. Поэтому свежий снимок уезжает в S3-совместимое
хранилище, а на диске остаётся немного последних копий.

Выгрузка намеренно необязательна: не заданы ключи — молча работаем как раньше,
только локально. Ошибка сети не должна ронять ежедневный таймер обслуживания —
бэкап уже сделан, потеря копии в облаке некритична и попадает в лог.
"""
import logging
from dataclasses import dataclass
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OffsiteResult:
    uploaded_key: str | None
    removed_remote: int
    error: str | None = None


def offsite_bucket() -> str:
    return settings.backup_s3_bucket or settings.s3_bucket


def offsite_enabled() -> bool:
    return bool(settings.s3_endpoint_url and offsite_bucket() and settings.s3_access_key)


def _client():
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region,
    )


def _prune_remote(client, bucket: str, keep: int) -> int:
    """Удаляет старые копии в бакете, оставляя keep самых свежих."""
    response = client.list_objects_v2(Bucket=bucket, Prefix=f"{settings.backup_s3_prefix}/")
    objects = response.get("Contents", [])
    if len(objects) <= keep:
        return 0

    stale = sorted(objects, key=lambda item: item["LastModified"], reverse=True)[keep:]
    for item in stale:
        client.delete_object(Bucket=bucket, Key=item["Key"])
    return len(stale)


def upload_backup(path: Path) -> OffsiteResult:
    """Кладёт файл бэкапа в облако и подчищает там старые копии."""
    if not offsite_enabled():
        logger.info("Offsite-бэкап выключен (нет S3-настроек) — копия только на диске")
        return OffsiteResult(None, 0)

    bucket = offsite_bucket()
    key = f"{settings.backup_s3_prefix}/{path.name}"
    try:
        client = _client()
        client.upload_file(str(path), bucket, key)
        removed = _prune_remote(client, bucket, settings.backup_offsite_keep)
    except Exception as error:  # noqa: BLE001 — сеть/креды/бакет: причин много, все не смертельны
        logger.exception("Не удалось выгрузить бэкап в S3 (%s)", bucket)
        return OffsiteResult(None, 0, error=str(error))

    logger.info("Бэкап выгружен: s3://%s/%s (удалено старых в облаке: %s)", bucket, key, removed)
    return OffsiteResult(key, removed)

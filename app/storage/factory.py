from app.config import settings
from app.storage.base import StorageBackend


def get_storage() -> StorageBackend:
    """S3, если задан s3_endpoint_url; иначе локальное файловое хранилище."""
    if settings.s3_endpoint_url and settings.s3_bucket:
        from app.storage.s3 import S3Storage

        return S3Storage(
            endpoint_url=settings.s3_endpoint_url,
            bucket=settings.s3_bucket,
            access_key=settings.s3_access_key,
            secret_key=settings.s3_secret_key,
            region=settings.s3_region,
        )

    from app.storage.local import LocalStorage

    return LocalStorage(settings.storage_dir)

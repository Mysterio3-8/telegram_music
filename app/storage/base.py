from typing import Protocol


class StorageBackend(Protocol):
    def save(self, key: str, data: bytes) -> str:
        """Сохраняет байты под ключом, возвращает storage_path для БД."""
        ...

    def load(self, key: str) -> bytes:
        ...

    def exists(self, key: str) -> bool:
        ...

    def delete(self, key: str) -> None:
        """Удаляет объект. Не должен падать, если ключа уже нет."""
        ...

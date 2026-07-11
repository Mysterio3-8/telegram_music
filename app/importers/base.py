from collections.abc import Iterator
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ImportItem:
    title: str
    artist: str
    duration: int  # секунды
    data: bytes
    file_format: str | None


class ImportSource(Protocol):
    """Источник каталога. Коннекторы к внешним сервисам реализуют этот интерфейс."""

    def items(self) -> Iterator[ImportItem]:
        ...

"""Список аудио-сообщений канала через Telethon. Возвращает только ссылки
(message_id + сырые метаданные) — сами байты скачиваются позже, отдельным
шагом, чтобы задачи сканирования и импорта оставались независимыми (как в
YouTube-модуле: video_id отдельно от скачивания)."""
from dataclasses import dataclass

from telethon import TelegramClient


@dataclass(frozen=True)
class AudioMessageRef:
    message_id: int
    posted_title: str | None
    posted_performer: str | None
    caption: str


async def list_audio_messages(
    client: TelegramClient, channel: str, min_id: int
) -> list[AudioMessageRef]:
    entity = await client.get_entity(channel)
    refs: list[AudioMessageRef] = []
    async for message in client.iter_messages(entity, min_id=min_id, reverse=True):
        if not message.audio:
            continue
        file = message.file
        refs.append(
            AudioMessageRef(
                message_id=message.id,
                posted_title=getattr(file, "title", None),
                posted_performer=getattr(file, "performer", None),
                caption=message.message or "",
            )
        )
    return refs

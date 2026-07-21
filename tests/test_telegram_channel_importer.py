from dataclasses import dataclass

from app.db.models import TelegramChannelImport, TelegramChannelSource, Track
from app.services.telegram_channel.importer import ImportError_, process_import


@dataclass
class FakeFile:
    title: str | None
    performer: str | None
    duration: int | None
    ext: str


@dataclass
class FakeMessage:
    id: int
    audio: bool
    file: FakeFile
    message: str


class FakeClient:
    def __init__(self, message: FakeMessage | None, data: bytes = b"fake-audio-bytes"):
        self._message = message
        self._data = data

    async def get_entity(self, channel: str) -> str:
        return channel

    async def get_messages(self, entity, ids: int):
        return self._message

    async def download_media(self, message) -> bytes:
        return self._data

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


@dataclass
class FakeSentAudio:
    file_id: str


class FakeSentMessage:
    def __init__(self, file_id: str):
        self.audio = FakeSentAudio(file_id)


class FakeBot:
    def __init__(self):
        self.calls = []

    async def send_audio(self, chat_id, audio, **kwargs):
        self.calls.append((chat_id, kwargs))
        return FakeSentMessage(file_id=f"tg_file_{len(self.calls)}")


async def make_source_and_import(session, message_id: int = 42) -> tuple[TelegramChannelSource, TelegramChannelImport]:
    source = TelegramChannelSource(channel="@mychannel", title="My Channel", status="active")
    session.add(source)
    await session.flush()
    imp = TelegramChannelImport(source_id=source.id, message_id=message_id, status="pending")
    session.add(imp)
    await session.commit()
    return source, imp


async def test_process_import_creates_track_with_metadata_from_audio_tags(session):
    source, imp = await make_source_and_import(session)
    message = FakeMessage(
        id=imp.message_id,
        audio=True,
        file=FakeFile(title="Акап", performer="DJ KL", duration=180, ext=".mp3"),
        message="",
    )
    client = FakeClient(message)
    bot = FakeBot()

    status = await process_import(session, bot, client, imp.id)

    assert status == "imported"
    await session.refresh(imp)
    assert imp.status == "imported"
    assert imp.detected_title == "Акап"
    assert imp.detected_artist == "DJ KL"
    track = await session.get(Track, imp.track_id)
    assert track.title == "Акап"
    assert track.artist == "DJ KL"
    assert track.tg_file_id == "tg_file_1"
    assert track.meta_synced is True
    assert track.storage_path == f"local://tracks/{track.id}"  # архив для стрима Mini App
    assert len(bot.calls) == 1


async def test_process_import_falls_back_to_caption_parsing(session):
    source, imp = await make_source_and_import(session)
    message = FakeMessage(
        id=imp.message_id,
        audio=True,
        file=FakeFile(title=None, performer=None, duration=120, ext=".mp3"),
        message="DJ KL - Новый трек",
    )
    client = FakeClient(message)
    bot = FakeBot()

    await process_import(session, bot, client, imp.id)

    await session.refresh(imp)
    assert imp.detected_artist == "DJ KL"
    assert imp.detected_title == "Новый трек"


async def test_process_import_skips_upload_for_metadata_duplicate(session):
    # ASCII-названия: SQLite lower() не приводит регистр кириллицы (известное
    # dev-ограничение, см. CLAUDE.md) — для проверки самого дедупа это не важно.
    source, imp = await make_source_and_import(session, message_id=99)
    existing = Track(title="Believer", artist="Imagine Dragons", duration=180, tg_file_id="already_here", meta_synced=True)
    session.add(existing)
    await session.commit()

    message = FakeMessage(
        id=imp.message_id,
        audio=True,
        file=FakeFile(title="Believer", performer="Imagine Dragons", duration=180, ext=".mp3"),
        message="",
    )
    client = FakeClient(message)
    bot = FakeBot()

    status = await process_import(session, bot, client, imp.id)

    assert status == "imported"
    await session.refresh(imp)
    assert imp.track_id == existing.id
    assert len(bot.calls) == 0  # дубликат — повторной заливки в Telegram не было


async def test_process_import_raises_when_message_has_no_audio(session):
    source, imp = await make_source_and_import(session)
    message = FakeMessage(id=imp.message_id, audio=False, file=FakeFile(None, None, None, ""), message="")
    client = FakeClient(message)
    bot = FakeBot()

    try:
        await process_import(session, bot, client, imp.id)
        assert False, "должно было упасть"
    except ImportError_:
        pass


async def test_process_import_is_idempotent_for_already_imported(session):
    source, imp = await make_source_and_import(session)
    imp.status = "imported"
    imp.track_id = None
    await session.commit()
    client = FakeClient(None)
    bot = FakeBot()

    status = await process_import(session, bot, client, imp.id)

    assert status == "imported"
    assert len(bot.calls) == 0


async def test_process_import_instrumental_target(session):
    """Источник с target=instrumentals кладёт аудио в базу минусов, не в треки."""
    from sqlalchemy import func, select

    from app.db.models import Instrumental

    source = TelegramChannelSource(
        channel="@zvyagaminus", title="Zvyaga", status="active", target="instrumentals"
    )
    session.add(source)
    await session.flush()
    imp = TelegramChannelImport(source_id=source.id, message_id=77, status="pending")
    session.add(imp)
    await session.commit()

    message = FakeMessage(
        id=77,
        audio=True,
        file=FakeFile(title="Night Beat", performer="Zvyaga", duration=140, ext=".mp3"),
        message="",
    )
    status = await process_import(session, FakeBot(), FakeClient(message), imp.id)

    assert status == "imported"
    await session.refresh(imp)
    assert imp.status == "imported"
    assert imp.track_id is None  # трек не создавался
    tracks_count = await session.scalar(select(func.count()).select_from(Track))
    assert tracks_count == 0
    instrumental = await session.scalar(select(Instrumental).limit(1))
    assert instrumental is not None
    assert instrumental.title == "Night Beat"
    assert instrumental.artist == "Zvyaga"
    assert instrumental.tg_file_id == "tg_file_1"
    assert instrumental.source == "tg_channel"

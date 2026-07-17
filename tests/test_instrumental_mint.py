from dataclasses import dataclass

from app.db.models import Instrumental
from app.services.catalog_import import (
    find_existing_instrumental,
    import_instrumental_via_telegram_mint,
)


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
        self.calls.append(chat_id)
        return FakeSentMessage(file_id=f"minus_file_{len(self.calls)}")


async def test_mint_creates_instrumental(session):
    bot = FakeBot()

    instrumental, created = await import_instrumental_via_telegram_mint(
        session,
        bot,
        title="Fire Beat",
        artist="Zvyaga",
        duration=120,
        file_format="mp3",
        data=b"fake-bytes",
        fingerprint="fp-1",
        archive_chat_id=777,
        source="soundcloud",
    )

    assert created is True
    assert instrumental.tg_file_id == "minus_file_1"
    assert instrumental.source == "soundcloud"
    assert bot.calls == [777]


async def test_mint_dedups_by_fingerprint(session):
    session.add(Instrumental(title="Old", artist="X", duration=100, fingerprint="fp-same"))
    await session.commit()
    bot = FakeBot()

    _instrumental, created = await import_instrumental_via_telegram_mint(
        session,
        bot,
        title="New Name",
        artist="Другой",
        duration=200,
        file_format="mp3",
        data=b"bytes",
        fingerprint="fp-same",
        archive_chat_id=777,
        source="tg_channel",
    )

    assert created is False
    assert bot.calls == []  # дубликат — в Telegram ничего не отправляли


async def test_find_existing_by_metadata(session):
    session.add(Instrumental(title="Night Beat", artist="Zvyaga", duration=150))
    await session.commit()

    found = await find_existing_instrumental(session, None, " night beat ", "ZVYAGA", 152)

    assert found is not None

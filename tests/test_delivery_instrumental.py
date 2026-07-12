from app.db.models import Instrumental
from app.handlers.delivery import send_instrumental_audio
from app.storage.local import LocalStorage


class FakeSentAudio:
    def __init__(self, file_id: str):
        self.file_id = file_id


class FakeSentMessage:
    def __init__(self, file_id: str):
        self.audio = FakeSentAudio(file_id)


class FakeBot:
    def __init__(self):
        self.calls = []

    async def send_audio(self, chat_id, audio, **kwargs):
        self.calls.append((chat_id, audio, kwargs))
        return FakeSentMessage(file_id=f"tg_file_{len(self.calls)}")


async def test_send_instrumental_audio_uses_cached_file_id(session):
    instrumental = Instrumental(title="Captain", artist="Miyagi", duration=180, tg_file_id="cached_id")
    session.add(instrumental)
    await session.commit()
    bot = FakeBot()

    message = await send_instrumental_audio(bot, 42, session, instrumental)

    assert message is not None
    assert bot.calls == [(42, "cached_id", {"reply_markup": None, "title": "Captain", "performer": "Miyagi"})]


async def test_send_instrumental_audio_loads_from_storage_and_caches_file_id(session, tmp_path, monkeypatch):
    storage = LocalStorage(str(tmp_path))
    storage_path = storage.save("instrumentals/1", b"raw-audio-bytes")
    monkeypatch.setattr("app.storage.get_storage", lambda: storage)

    instrumental = Instrumental(id=1, title="Captain", artist="Miyagi", duration=180, storage_path=storage_path)
    session.add(instrumental)
    await session.commit()
    bot = FakeBot()

    message = await send_instrumental_audio(bot, 42, session, instrumental)

    assert message is not None
    assert instrumental.tg_file_id == "tg_file_1"


async def test_send_instrumental_audio_returns_none_without_source(session):
    instrumental = Instrumental(title="Captain", artist="Miyagi", duration=180)
    session.add(instrumental)
    await session.commit()
    bot = FakeBot()

    message = await send_instrumental_audio(bot, 42, session, instrumental)

    assert message is None

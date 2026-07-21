from app.db.models import Track, YoutubeImport, YoutubeSource
from app.services.youtube import importer
from app.services.youtube.downloader import DownloadedAudio


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
        self.calls.append((chat_id, kwargs))
        return FakeSentMessage(file_id=f"tg_file_{len(self.calls)}")


async def make_source_and_import(session, video_id: str = "vid00000001") -> tuple[YoutubeSource, YoutubeImport]:
    source = YoutubeSource(url="https://youtube.com/@ch", title="My Channel", status="active")
    session.add(source)
    await session.flush()
    imp = YoutubeImport(source_id=source.id, video_id=video_id, video_title="raw", status="pending")
    session.add(imp)
    await session.commit()
    return source, imp


async def test_process_import_mints_via_bot_and_archives(session, monkeypatch):
    source, imp = await make_source_and_import(session)
    audio = DownloadedAudio(
        data=b"fake-audio-bytes", file_format="mp3", duration=200, video_title="DJ KL - Track One"
    )
    monkeypatch.setattr(importer, "download_audio", lambda video_id: audio)
    bot = FakeBot()

    status = await importer.process_import(session, bot, imp.id)

    assert status == "imported"
    await session.refresh(imp)
    assert imp.status == "imported"
    assert imp.detected_artist == "DJ KL"
    assert imp.detected_title == "Track One"
    track = await session.get(Track, imp.track_id)
    assert track.tg_file_id == "tg_file_1"
    assert track.meta_synced is True
    assert track.storage_path == f"local://tracks/{track.id}"  # архив для стрима Mini App
    assert len(bot.calls) == 1


async def test_process_import_skips_upload_for_duplicate(session, monkeypatch):
    existing = Track(title="Track One", artist="DJ KL", duration=200, tg_file_id="already", meta_synced=True)
    session.add(existing)
    await session.commit()
    source, imp = await make_source_and_import(session, video_id="vid00000002")
    audio = DownloadedAudio(
        data=b"fake-audio-bytes", file_format="mp3", duration=200, video_title="DJ KL - Track One"
    )
    monkeypatch.setattr(importer, "download_audio", lambda video_id: audio)
    bot = FakeBot()

    status = await importer.process_import(session, bot, imp.id)

    assert status == "imported"
    await session.refresh(imp)
    assert imp.track_id == existing.id
    assert len(bot.calls) == 0  # дубликат — повторной заливки не было


async def test_process_import_raises_when_download_fails(session, monkeypatch):
    source, imp = await make_source_and_import(session)
    monkeypatch.setattr(importer, "download_audio", lambda video_id: None)
    bot = FakeBot()

    try:
        await importer.process_import(session, bot, imp.id)
        assert False, "должно было упасть"
    except importer.ImportError_:
        pass

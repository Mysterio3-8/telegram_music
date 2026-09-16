"""Альбомы в боте (16.09): клавиатуры, «скачать весь» только с Premium, выкачка."""
from dataclasses import asdict
from types import SimpleNamespace

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import models  # noqa: F401
from app.db.base import Base
from app.db.models import User
from app.handlers import album_search
from app.keyboards.albums import album_keyboard, album_rows
from app.services.albums import AlbumCandidate
from app.services.track_lookup.ranking import Candidate
from app.tasks import album_fetch

ALBUM = AlbumCandidate(
    id=970298674, title="2004", artist="Скриптонит", url="https://soundcloud.com/s/sets/2004y",
    track_count=24, cover_url=None, kind="album", official=True, likes=11466,
)


def _tracks(count):
    return [
        Candidate(source="soundcloud", url=f"https://soundcloud.com/s/{i}", title=f"Трек {i}", duration=180, artist="Скриптонит")
        for i in range(1, count + 1)
    ]


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row]


def test_album_rows_under_results():
    assert album_rows([]) == []
    rows = album_rows([ALBUM])
    assert rows[0][0].callback_data == "qs:noop"  # заголовок «💿 Альбомы»
    assert rows[1][0].callback_data == "al:o:0"
    assert "2004" in rows[1][0].text and "24" in rows[1][0].text


def test_album_keyboard_pages_download_and_back():
    tracks = _tracks(24)
    first = _callbacks(album_keyboard(tracks, page=1))
    assert first[:10] == [f"al:t:{i}" for i in range(10)]
    assert "al:p:2" in first and "al:p:0" not in first
    assert "al:all" in first and "qs:p:1" in first
    last = _callbacks(album_keyboard(tracks, page=3))
    assert [c for c in last if c.startswith("al:t:")] == ["al:t:20", "al:t:21", "al:t:22", "al:t:23"]
    assert "al:p:2" in last and "al:p:4" not in last


class FakeMessage:
    def __init__(self):
        self.chat = SimpleNamespace(id=555)
        self.answers = []

    async def answer(self, text, reply_markup=None):
        self.answers.append((text, reply_markup))


class FakeCallback:
    def __init__(self, data):
        self.data = data
        self.from_user = SimpleNamespace(id=555)
        self.message = FakeMessage()
        self.alerts = []

    async def answer(self, text=None, show_alert=False):
        self.alerts.append((text, show_alert))


class _NoSession:
    async def __aenter__(self):
        return None

    async def __aexit__(self, *exc):
        return False


@pytest.fixture
def fsm():
    return FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=555, user_id=555))


@pytest.fixture
def queued(monkeypatch):
    calls = []
    monkeypatch.setattr(album_search, "session_factory", _NoSession)

    async def fake_user(session, tg_user):
        return SimpleNamespace(telegram_id=tg_user.id)

    monkeypatch.setattr(album_search, "ensure_user", fake_user)
    monkeypatch.setattr(album_fetch.album_fetch_all, "delay", lambda **kw: calls.append(kw))
    return calls


async def _prepare(fsm, count=24):
    await fsm.update_data(al_album=ALBUM.as_dict(), al_tracks=[asdict(t) for t in _tracks(count)])


async def test_download_all_requires_premium(fsm, queued, monkeypatch):
    await _prepare(fsm)
    monkeypatch.setattr(album_search, "is_premium_active", lambda user: False)
    callback = FakeCallback("al:all")
    await album_search.album_download_all(callback, fsm)
    assert queued == []
    assert callback.alerts[0][1] is True  # алерт «с Premium»
    text, markup = callback.message.answers[0]
    assert "menu:premium" in _callbacks(markup)


async def test_download_all_queues_once_with_lock(fsm, queued, monkeypatch):
    await _prepare(fsm)
    monkeypatch.setattr(album_search, "is_premium_active", lambda user: True)
    locked = set()

    def acquire(telegram_id):
        if telegram_id in locked:
            return False
        locked.add(telegram_id)
        return True

    monkeypatch.setattr(album_search, "acquire_album_lock", acquire)
    first = FakeCallback("al:all")
    await album_search.album_download_all(first, fsm)
    assert len(queued) == 1 and len(queued[0]["tracks"]) == 24
    assert queued[0]["chat_id"] == 555 and queued[0]["album"]["title"] == "2004"
    assert "5" in first.message.answers[0][0]  # «около 5 мин»

    second = FakeCallback("al:all")
    await album_search.album_download_all(second, fsm)
    assert len(queued) == 1 and second.alerts[0][1] is True  # «альбом уже качается»


async def test_stale_album_state_is_reported(fsm, queued):
    callback = FakeCallback("al:all")
    await album_search.album_download_all(callback, fsm)
    assert callback.alerts and callback.alerts[0][1] is True and queued == []


class FakeBot:
    def __init__(self):
        self.messages = []
        self.audio = []

    async def send_message(self, chat_id, text, reply_markup=None):
        message = SimpleNamespace(text=text)

        async def edit_text(new_text):
            message.text = new_text

        message.edit_text = edit_text
        self.messages.append(message)
        return message

    async def send_audio(self, chat_id, file_id, caption=None):
        self.audio.append((file_id, caption))


async def test_run_album_delivers_and_reports_failures(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as seed:
        seed.add(User(telegram_id=555, ui_language="ru"))
        await seed.commit()

    released = []
    monkeypatch.setattr("app.services.albums.release_album_lock", lambda tid: released.append(tid))
    monkeypatch.setattr(album_fetch, "SEND_PAUSE_SECONDS", 0)
    recorded = []

    async def fake_record(session, user_id, track_id, event, source="unknown"):
        recorded.append((track_id, event, source))

    monkeypatch.setattr("app.services.stats.record_event", fake_record)

    async def fake_import(session, bot, candidate, telegram_id, save_to_library=True):
        if candidate.title == "Трек 2":
            raise RuntimeError("DRM, замен не нашлось")
        number = int(candidate.title.split()[-1])
        return SimpleNamespace(id=number, tg_file_id=f"file{number}", artist=candidate.artist, title=candidate.title), True

    monkeypatch.setattr("app.services.track_lookup.importer.import_candidate", fake_import)

    bot = FakeBot()
    delivered, failed = await album_fetch.run_album(
        ALBUM.as_dict(), [asdict(t) for t in _tracks(3)], 555, 555, bot=bot, factory=factory
    )
    assert delivered == 2 and failed == ["Скриптонит — Трек 2"]
    assert [file_id for file_id, _ in bot.audio] == ["file1", "file3"]
    assert bot.audio[0][1].startswith("💿 1/3")
    assert bot.messages[0].text.endswith("3 из 3")  # прогресс дошёл до конца
    assert "2 из 3" in bot.messages[-1].text and "Трек 2" in bot.messages[-1].text
    assert released == [555]  # замок снят даже с упавшим треком
    assert recorded == [(1, "download", "worker"), (3, "download", "worker")]
    await engine.dispose()

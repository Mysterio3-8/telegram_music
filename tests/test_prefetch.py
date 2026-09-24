"""Предзагрузка верха выдачи (19.09): к нажатию трек уже в базе, как в @RuMediaBot."""
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db import models  # noqa: F401
from app.db.base import Base
from app.db.models import Track
from app.handlers import quick_search
from app.services import prefetch
from app.services.track_lookup.ranking import Candidate


def _cands(count):
    return [
        Candidate(source="soundcloud", url=f"https://soundcloud.com/a/{i}", title=f"T{i}", duration=180, artist="A")
        for i in range(count)
    ]


def test_pick_takes_shown_page_without_known():
    # Прогреваем всю показанную страницу (владелец 21.09: «выдаётся 20 треков…
    # минтятся и остальные»), а не первые три, как было до 22.09.
    cands = _cands(30)
    picked = prefetch.pick_for_prefetch(cands, set())
    assert [c.url for c in picked] == [c.url for c in cands[: prefetch.PREFETCH_TOP]]
    # Уже залитый из верха не заменяется следующим за страницей: качаем ровно то,
    # что человек видит, а не добираем хвост выдачи
    picked = prefetch.pick_for_prefetch(cands, {cands[0].url})
    assert [c.url for c in picked] == [c.url for c in cands[1 : prefetch.PREFETCH_TOP]]


def test_without_redis_no_slot(monkeypatch):
    # Без общего слота предзагрузка заняла бы оба потока воркера — лучше её не делать
    monkeypatch.setattr(prefetch, "_redis", lambda: None)
    assert prefetch.acquire_slot() is False
    assert prefetch.is_prefetching("x") is False


class _FakeRedis:
    def __init__(self, queue_len=0):
        self.queue_len = queue_len
        self.expired = []

    def llen(self, _key):
        return self.queue_len

    def expire(self, key, ttl):
        self.expired.append((key, ttl))


def test_yields_while_user_waits(monkeypatch):
    # 21.09: предзагрузка заняла оба потока воркера, и нажатие ждало 3 минуты
    monkeypatch.setattr(prefetch, "_redis", lambda: _FakeRedis(queue_len=2))
    assert prefetch.user_waiting() is True
    monkeypatch.setattr(prefetch, "_redis", lambda: _FakeRedis(queue_len=0))
    assert prefetch.user_waiting() is False


def test_slot_is_refreshed_between_tracks(monkeypatch):
    # Замок должен переживать всю работу: истёк на ходу — запускалась вторая
    fake = _FakeRedis()
    monkeypatch.setattr(prefetch, "_redis", lambda: fake)
    prefetch.refresh_slot()
    assert fake.expired == [("prefetch:slot", prefetch.SLOT_TTL_SECONDS)]
    assert prefetch.SLOT_TTL_SECONDS >= 300


@pytest.fixture
async def factory(monkeypatch):
    # StaticPool: иначе параллельная сессия получает новую пустую базу в памяти
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(quick_search, "session_factory", maker)
    monkeypatch.setattr(quick_search, "_PREFETCH_POLL_SECONDS", 0.01)
    yield maker
    await engine.dispose()


async def test_wait_returns_track_once_prefetch_lands(factory, monkeypatch):
    # Воркер дописывает трек на третьей проверке — бот должен его дождаться
    monkeypatch.setattr(prefetch, "is_prefetching", lambda _url: True)
    calls = {"n": 0}
    landed = SimpleNamespace(id=1, tg_file_id="F")

    async def fake_find(_session, _url):
        calls["n"] += 1
        return landed if calls["n"] >= 3 else None

    monkeypatch.setattr(quick_search, "find_track_by_source_url", fake_find)
    track = await quick_search._wait_prefetched("https://soundcloud.com/a/1")
    assert track is landed and calls["n"] == 3


async def test_wait_gives_up_when_prefetch_failed(factory, monkeypatch):
    monkeypatch.setattr(prefetch, "is_prefetching", lambda _url: False)
    assert await quick_search._wait_prefetched("https://soundcloud.com/a/404") is None


async def test_schedule_skips_known_and_queues_rest(factory, monkeypatch):
    cands = _cands(5)
    async with factory() as session:
        session.add(Track(title="T0", artist="A", duration=180, source_url=cands[0].url, tg_file_id="F"))
        await session.commit()

    sent = {}

    class FakeTask:
        @staticmethod
        def apply_async(kwargs, expires):
            sent.update(kwargs, expires=expires)

    import app.tasks.search_fetch as search_fetch

    monkeypatch.setattr(search_fetch, "search_prefetch", FakeTask)
    await quick_search._schedule_prefetch(cands, telegram_id=7)
    assert [row["url"] for row in sent["candidates"]] == [c.url for c in cands[1:]]
    assert sent["telegram_id"] == 7 and sent["expires"] == 60


async def test_schedule_nothing_when_top_known(factory, monkeypatch):
    cands = _cands(2)
    async with factory() as session:
        for c in cands:
            session.add(Track(title=c.title, artist="A", duration=180, source_url=c.url, tg_file_id="F"))
        await session.commit()
    import app.tasks.search_fetch as search_fetch

    monkeypatch.setattr(search_fetch, "search_prefetch", SimpleNamespace(apply_async=lambda **_: pytest.fail("не должно")))
    await quick_search._schedule_prefetch(cands, telegram_id=7)

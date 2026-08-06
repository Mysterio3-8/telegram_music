"""Антиспам-мидлварь: гасит флуд, не мешает нормальному использованию."""
import pytest

from aiogram.types import Message

from app.i18n import t
from app.config import settings
from app.middlewares import throttling
from app.middlewares.throttling import ThrottlingMiddleware


class _FakeUser:
    def __init__(self, user_id: int) -> None:
        self.id = user_id


# Настоящий aiogram-Message (мидлварь различает типы через isinstance, поэтому
# подделка классом-заглушкой проверяла бы не то, что работает в проде).
# model_construct — без валидации: нужен только тип и .answer().
def _FakeMessage() -> Message:
    return Message.model_construct(message_id=1, text="запрос")


# Все предупреждения за тест — одним списком: привязывать к id(message) нельзя,
# CPython переиспользует id освобождённых объектов, и учёт «плыл».
_sent: list[str] = []


@pytest.fixture(autouse=True)
def _capture_answers(monkeypatch):
    """Перехватываем Message.answer: без бота настоящая отправка невозможна."""
    async def fake_answer(_self, text: str, **_kwargs) -> None:
        _sent.append(text)

    monkeypatch.setattr(Message, "answer", fake_answer, raising=False)
    _sent.clear()
    yield


@pytest.fixture
def clock(monkeypatch):
    """Управляемое время — тесты не спят по-настоящему."""
    current = {"now": 1000.0}
    monkeypatch.setattr(throttling.time, "monotonic", lambda: current["now"])
    return current


@pytest.fixture(autouse=True)
def _no_admins(monkeypatch):
    monkeypatch.setattr(settings, "admin_ids", "")


async def _call(middleware, event, user_id: int, calls: list[int]):
    async def handler(_event, _data):
        calls.append(user_id)
        return "handled"

    return await middleware(handler, event, {"event_from_user": _FakeUser(user_id)})


@pytest.mark.asyncio
async def test_normal_pace_passes(clock):
    middleware = ThrottlingMiddleware()
    calls: list[int] = []
    for _ in range(5):
        result = await _call(middleware, _FakeMessage(), 1, calls)
        assert result == "handled"
        clock["now"] += 2.0  # спокойный темп
    assert len(calls) == 5


@pytest.mark.asyncio
async def test_instant_repeat_blocked(clock):
    """Два сообщения подряд без паузы — второе не доходит до хендлера."""
    middleware = ThrottlingMiddleware()
    calls: list[int] = []
    await _call(middleware, _FakeMessage(), 1, calls)
    result = await _call(middleware, _FakeMessage(), 1, calls)
    assert result is None
    assert len(calls) == 1
    assert _sent == [t("common.throttled")]


@pytest.mark.asyncio
async def test_burst_blocked_then_released(clock):
    middleware = ThrottlingMiddleware()
    calls: list[int] = []
    # держим интервал выше порога, но давим много подряд — сработает burst-лимит
    for _ in range(throttling.BURST_LIMIT + 3):
        await _call(middleware, _FakeMessage(), 1, calls)
        clock["now"] += throttling.THROTTLE_SECONDS + 0.05
    assert len(calls) <= throttling.BURST_LIMIT

    clock["now"] += throttling.BLOCK_SECONDS + throttling.BURST_WINDOW + 1
    before = len(calls)
    assert await _call(middleware, _FakeMessage(), 1, calls) == "handled"
    assert len(calls) == before + 1


@pytest.mark.asyncio
async def test_warning_sent_once_per_series(clock):
    """Флудеру не отвечаем на каждое сообщение — иначе флудим сами."""
    middleware = ThrottlingMiddleware()
    calls: list[int] = []
    await _call(middleware, _FakeMessage(), 1, calls)
    for _ in range(5):
        await _call(middleware, _FakeMessage(), 1, calls)
    assert _sent == [t("common.throttled")]  # ровно одно предупреждение на серию


@pytest.mark.asyncio
async def test_users_isolated(clock):
    """Флуд одного не блокирует другого."""
    middleware = ThrottlingMiddleware()
    calls: list[int] = []
    await _call(middleware, _FakeMessage(), 1, calls)
    await _call(middleware, _FakeMessage(), 1, calls)  # первый в блоке
    assert await _call(middleware, _FakeMessage(), 2, calls) == "handled"


@pytest.mark.asyncio
async def test_admin_never_throttled(clock, monkeypatch):
    monkeypatch.setattr(settings, "admin_ids", "777")
    middleware = ThrottlingMiddleware()
    calls: list[int] = []
    for _ in range(30):
        assert await _call(middleware, _FakeMessage(), 777, calls) == "handled"
    assert len(calls) == 30

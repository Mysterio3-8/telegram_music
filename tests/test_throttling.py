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


@pytest.mark.asyncio
async def test_machine_burst_blocks_for_a_minute(clock):
    """Больше 20 нажатий в секунду — это скрипт, а не человек: пауза минута.

    Требование владельца. Обычный флуд гасится на 20 секунд, машинный — дольше,
    чтобы одна вкладка с автокликером не держала воркер занятым.
    """
    middleware = ThrottlingMiddleware()
    calls: list[int] = []
    for _ in range(25):
        await _call(middleware, _FakeMessage(), 1, calls)
        clock["now"] += 0.01  # 100 нажатий в секунду

    # Обычная блокировка к этому моменту истекла бы, машинная — ещё держит
    clock["now"] += throttling.BLOCK_SECONDS + 1
    assert await _call(middleware, _FakeMessage(), 1, calls) is None
    clock["now"] += throttling.RAPID_BLOCK_SECONDS
    assert await _call(middleware, _FakeMessage(), 1, calls) == "handled"


# --- счётчики не растут вечно ------------------------------------------------------


async def test_idle_users_are_swept_out(clock):
    """⚠️ Очереди меток чистились сами, а КЛЮЧИ не удалялись никогда: каждый, кто
    хоть раз написал боту, навсегда оставлял по записи в шести структурах. При
    37 пользователях незаметно, но бот растёт вирально, и на сотне тысяч это
    десятки мегабайт, которые процесс уже не отдаст — на боксе, где воркер
    трижды падал по OOM."""
    middleware = ThrottlingMiddleware()
    calls: list[int] = []

    for user_id in range(1, 21):
        await _call(middleware, _FakeMessage(), user_id, calls)
    assert len(middleware._last_action) == 20

    # Прошло больше срока хранения, пришёл новый человек — старые уходят
    clock["now"] += throttling.RETENTION_SECONDS + throttling.SWEEP_EVERY_SECONDS
    await _call(middleware, _FakeMessage(), 999, calls)

    assert list(middleware._last_action) == [999]
    assert not middleware._history.keys() - {999}
    assert middleware._warned == set()


async def test_sweep_keeps_active_users(clock):
    """Уборка не должна снимать блокировку с того, кто флудит прямо сейчас."""
    middleware = ThrottlingMiddleware()
    calls: list[int] = []

    await _call(middleware, _FakeMessage(), 7, calls)
    clock["now"] += 0.1
    await _call(middleware, _FakeMessage(), 7, calls)  # слишком быстро → блокировка
    assert middleware._blocked_until.get(7, 0) > clock["now"]

    # Уборка через её интервал, но человек активен — запись должна уцелеть
    clock["now"] += throttling.SWEEP_EVERY_SECONDS + 1
    blocked_before = middleware._blocked_until.get(7)
    middleware._sweep(clock["now"])
    assert middleware._blocked_until.get(7) == blocked_before


async def test_sweep_runs_rarely(clock):
    """Перебор словарей в горячем пути на каждое сообщение — лишние такты."""
    middleware = ThrottlingMiddleware()
    calls: list[int] = []

    await _call(middleware, _FakeMessage(), 1, calls)
    first_sweep = middleware._last_sweep
    clock["now"] += 1.0
    await _call(middleware, _FakeMessage(), 2, calls)

    assert middleware._last_sweep == first_sweep

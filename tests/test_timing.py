"""Замер времени обработки: в лог попадает только то, что реально тормозило."""
import logging

import pytest
from aiogram.types import CallbackQuery, Message

from app.middlewares import timing
from app.middlewares.timing import TimingMiddleware, describe_event


def _message(text: str = "запрос") -> Message:
    return Message.model_construct(message_id=1, text=text)


def _callback(data: str) -> CallbackQuery:
    return CallbackQuery.model_construct(id="1", data=data)


@pytest.fixture
def clock(monkeypatch):
    """Управляемый перф-счётчик — тест не спит по-настоящему."""
    current = {"now": 0.0}
    monkeypatch.setattr(timing.time, "perf_counter", lambda: current["now"])
    return current


async def _run(middleware: TimingMiddleware, event, elapsed: float, clock) -> str:
    async def handler(_event, _data):
        clock["now"] += elapsed
        return "готово"

    return await middleware(handler, event, {})


@pytest.mark.asyncio
async def test_fast_update_leaves_log_empty(clock, caplog):
    with caplog.at_level(logging.WARNING):
        result = await _run(TimingMiddleware(), _message(), 0.2, clock)

    assert result == "готово"
    assert caplog.records == []


@pytest.mark.asyncio
async def test_slow_update_is_logged_with_duration(clock, caplog):
    with caplog.at_level(logging.WARNING):
        await _run(TimingMiddleware(), _message(), 4.5, clock)

    assert len(caplog.records) == 1
    assert "МЕДЛЕННО" in caplog.text
    assert "4.5 сек" in caplog.text


@pytest.mark.asyncio
async def test_slow_handler_is_logged_even_when_it_raises(clock, caplog):
    """Упавший хендлер — самый интересный случай, его нельзя терять."""
    async def failing_handler(_event, _data):
        clock["now"] += 9.0
        raise RuntimeError("сломалось")

    with caplog.at_level(logging.WARNING):
        with pytest.raises(RuntimeError):
            await TimingMiddleware()(failing_handler, _message(), {})

    assert "МЕДЛЕННО" in caplog.text


def test_describe_event_distinguishes_commands_callbacks_and_text():
    assert describe_event(_message("/start")) == "command /start"
    assert describe_event(_message("кизару")) == "text"
    assert describe_event(_callback("menu:main")) == "callback menu:main"

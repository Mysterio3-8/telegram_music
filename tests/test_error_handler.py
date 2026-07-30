"""Глобальный обработчик ошибок: падение хендлера не роняет бота и не оставляет
пользователя без ответа (требование владельца «бот никогда не должен падать»)."""
import pytest
from aiogram.types import ErrorEvent, Message, Update

from app.handlers.errors import FRIENDLY_TEXT, handle_any_error

_sent: list[str] = []


@pytest.fixture(autouse=True)
def _capture_answers(monkeypatch):
    async def fake_answer(_self, text: str, **_kwargs) -> None:
        _sent.append(text)

    monkeypatch.setattr(Message, "answer", fake_answer, raising=False)
    _sent.clear()
    yield


@pytest.mark.asyncio
async def test_reports_error_and_answers_user():
    update = Update.model_construct(
        update_id=1, message=Message.model_construct(message_id=1), callback_query=None
    )
    event = ErrorEvent.model_construct(update=update, exception=RuntimeError("бум"))

    handled = await handle_any_error(event)

    assert handled is True  # иначе aiogram поднимет исключение выше
    assert _sent == [FRIENDLY_TEXT]


@pytest.mark.asyncio
async def test_survives_when_answer_fails(monkeypatch):
    """Если ответить пользователю не удалось (чат заблокирован) — не падаем."""
    async def boom(_self, *_args, **_kwargs):
        raise RuntimeError("chat is blocked")

    monkeypatch.setattr(Message, "answer", boom, raising=False)
    update = Update.model_construct(
        update_id=1, message=Message.model_construct(message_id=1), callback_query=None
    )
    event = ErrorEvent.model_construct(update=update, exception=ValueError("исходная"))

    assert await handle_any_error(event) is True


@pytest.mark.asyncio
async def test_handles_update_without_message():
    """Апдейт без сообщения (например, inline) — обработчик не должен ломаться."""
    update = Update.model_construct(update_id=1, message=None, callback_query=None)
    event = ErrorEvent.model_construct(update=update, exception=RuntimeError("бум"))

    assert await handle_any_error(event) is True
    assert _sent == []

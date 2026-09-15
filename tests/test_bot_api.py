"""Лёгкий клиент Bot API процесса Mini App (services/bot_api.py)."""
import aiohttp
import pytest

from app.services import bot_api
from app.services.bot_api import BotApi, BotApiError
from app.services.subscription import check_channel_membership, is_bot_admin_of_channel


class _Response:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status = status

    async def json(self, content_type=None):
        return self._payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False


class _Session:
    def __init__(self, payload=None, error=None):
        self.payload = payload
        self.error = error
        self.calls = []
        self.closed = False

    def post(self, url, json=None, timeout=None):
        self.calls.append((url, json))
        if self.error is not None:
            raise self.error
        return _Response(self.payload)

    async def close(self):
        self.closed = True


def _client(monkeypatch, **session_kwargs) -> tuple[BotApi, _Session]:
    client = BotApi(token="123:SECRET")
    session = _Session(**session_kwargs)
    monkeypatch.setattr(client, "_session", lambda: session)
    return client, session


async def test_get_chat_member_parses_result(monkeypatch):
    client, session = _client(
        monkeypatch, payload={"ok": True, "result": {"status": "member", "user": {"id": 5}}}
    )
    member = await client.get_chat_member(chat_id="@chan", user_id=5)
    assert member.status == "member"
    assert session.calls[0][1] == {"chat_id": "@chan", "user_id": 5}
    assert session.calls[0][0].endswith("/getChatMember")


async def test_telegram_error_is_bot_api_error(monkeypatch):
    client, _ = _client(monkeypatch, payload={"ok": False, "description": "Bad Request: chat not found"})
    with pytest.raises(BotApiError, match="chat not found"):
        await client.get_chat_member(chat_id="@nope", user_id=5)


async def test_network_error_does_not_leak_token(monkeypatch):
    """Токен в URL запроса: текст ошибки aiohttp мог бы унести его в журнал."""
    client, _ = _client(
        monkeypatch, error=aiohttp.ClientError("https://api.telegram.org/bot123:SECRET/getMe")
    )
    with pytest.raises(BotApiError) as caught:
        await client.get_me()
    assert "SECRET" not in str(caught.value)
    assert caught.value.__cause__ is None and caught.value.__suppress_context__


class _LiteBot:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error

    async def get_me(self):
        return bot_api.SimpleNamespace(id=42)

    async def get_chat_member(self, chat_id, user_id):
        if self.error:
            raise self.error
        return bot_api.SimpleNamespace(**self.result)


async def test_subscription_accepts_lite_client_answers():
    assert await check_channel_membership(_LiteBot({"status": "creator"}), 1, "@c") is True
    assert await check_channel_membership(_LiteBot({"status": "left"}), 1, "@c") is False
    restricted_in = _LiteBot({"status": "restricted", "is_member": True})
    assert await check_channel_membership(restricted_in, 1, "@c") is True
    assert await check_channel_membership(_LiteBot({"status": "restricted", "is_member": False}), 1, "@c") is False


async def test_subscription_treats_lite_client_error_as_no_answer():
    """Сбой Telegram — «не ответил» (None), а не «не подписан» (False)."""
    assert await check_channel_membership(_LiteBot(error=BotApiError("boom")), 1, "@c") is None
    assert await is_bot_admin_of_channel(_LiteBot(error=BotApiError("boom")), "@c") is False
    assert await is_bot_admin_of_channel(_LiteBot({"status": "administrator"}), "@c") is True

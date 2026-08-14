"""Работа в группах — пункт 6 спеки 13.08.

Правило, которое здесь стережётся: в общем чате бот отвечает ТОЛЬКО на прямое
обращение и не устраивает ничего личного — ни гейта подписки, ни рекламы, ни
диалоговых мастеров.
"""
import time
import types

import pytest

from app.chat_scope import is_group, is_private
from app.middlewares.throttling import (
    CHAT_BURST_LIMIT,
    ThrottlingMiddleware,
)


def _chat(kind: str, chat_id: int = -100123):
    return types.SimpleNamespace(id=chat_id, type=kind)


def _message(text: str, kind: str = "private", reply_from_bot: bool | None = None):
    reply = None
    if reply_from_bot is not None:
        reply = types.SimpleNamespace(
            from_user=types.SimpleNamespace(is_bot=reply_from_bot)
        )
    return types.SimpleNamespace(text=text, chat=_chat(kind), reply_to_message=reply)


# --- где мы находимся ----------------------------------------------------------


def test_chat_scope_basics():
    assert is_private(_message("x", "private"))
    assert not is_group(_message("x", "private"))
    for kind in ("group", "supergroup"):
        assert is_group(_message("x", kind))
        assert not is_private(_message("x", kind))


def test_unknown_chat_counts_as_private():
    """Так вёл себя весь прежний код. Менять поведение там, где мы не уверены,
    опаснее, чем оставить как было."""
    assert is_private(types.SimpleNamespace(text="x"))


# --- кому адресовано сообщение --------------------------------------------------


def _query(message):
    from app.handlers.quick_search import _query_from

    return _query_from(message)


def test_private_chat_takes_any_text(monkeypatch):
    assert _query(_message("кизару")) == "кизару"
    assert _query(_message("   ")) is None


def test_group_ignores_ordinary_talk(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "bot_username", "muz_damn_bot")
    # Обычная реплика участников — бот в неё не встревает
    assert _query(_message("ребят, а что за трек играл вчера", "supergroup")) is None


def test_group_answers_on_mention(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "bot_username", "muz_damn_bot")
    # Упоминание вырезается: искать «@muz_damn_bot кизару» бессмысленно
    assert _query(_message("@muz_damn_bot кизару фейк айди", "supergroup")) == "кизару фейк айди"
    assert _query(_message("кизару @MUZ_DAMN_BOT", "supergroup")) == "кизару"
    # Упоминание без запроса — искать нечего
    assert _query(_message("@muz_damn_bot", "supergroup")) is None


def test_group_answers_on_reply_to_bot(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "bot_username", "muz_damn_bot")
    assert _query(_message("ещё этого артиста", "supergroup", reply_from_bot=True)) == (
        "ещё этого артиста"
    )
    # Ответ на сообщение человека — не наше дело
    assert _query(_message("ещё этого артиста", "supergroup", reply_from_bot=False)) is None


# --- антифлуд по чату ------------------------------------------------------------


def test_chat_bucket_catches_crowd_flood():
    """Лимиты по пользователю в группе не защищают: десять человек по одному
    действию — это десять действий, и каждый в своём праве, а платит за них наш
    единственный воркер."""
    middleware = ThrottlingMiddleware()
    now = time.monotonic()

    for _ in range(CHAT_BURST_LIMIT):
        assert middleware._chat_is_flooding(-100500, now) is False
    assert middleware._chat_is_flooding(-100500, now) is True
    # Соседний чат при этом не страдает
    assert middleware._chat_is_flooding(-100999, now) is False


def test_chat_bucket_forgets_old_actions():
    from app.middlewares.throttling import CHAT_BURST_WINDOW

    middleware = ThrottlingMiddleware()
    start = time.monotonic()
    for _ in range(CHAT_BURST_LIMIT):
        middleware._chat_is_flooding(-1, start)
    # Окно прошло — счётчик пуст, блокировка истекла
    later = start + CHAT_BURST_WINDOW + 60
    assert middleware._chat_is_flooding(-1, later) is False


# --- гейт подписки и реклама ------------------------------------------------------


@pytest.mark.asyncio
async def test_subscription_gate_skipped_in_groups():
    """Гейт в группе сделал бы бота немым: он отвечает всем сразу, а
    is_fully_subscribed ещё и fail-closed — первая ошибка API и тишина."""
    from app.middlewares.subscription import SubscriptionMiddleware

    called = False

    async def handler(event, data):
        nonlocal called
        called = True
        return "ok"

    event = _message("кизару", "supergroup")
    data = {"event_chat": _chat("supergroup"), "event_from_user": types.SimpleNamespace(id=1)}
    assert await SubscriptionMiddleware()(handler, event, data) == "ok"
    assert called


@pytest.mark.asyncio
async def test_ads_not_shown_in_groups():
    """«Купи Premium» в чужом чате — спам от нашего имени, за который бота
    выгоняют, а не покупают подписку."""
    from app.middlewares.ads import AdMiddleware

    shown = False

    async def handler(event, data):
        return "ok"

    middleware = AdMiddleware(frequency=1)

    async def _show_ad(event, telegram_id):
        nonlocal shown
        shown = True

    middleware._show_ad = _show_ad

    data = {"event_chat": _chat("supergroup"), "event_from_user": types.SimpleNamespace(id=1)}
    assert await middleware(handler, _message("x", "supergroup"), data) == "ok"
    assert not shown

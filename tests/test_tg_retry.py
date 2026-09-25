"""Флуд-контроль Telegram не должен терять трек (живой прогон 25.09, альбом 20 из 23)."""
import asyncio

import pytest
from aiogram.exceptions import TelegramRetryAfter
from aiogram.methods import SendAudio

from app.services import tg_retry


def _flood(seconds):
    return TelegramRetryAfter(method=SendAudio(chat_id=1, audio="x"), message="Too Many Requests", retry_after=seconds)


def test_waits_and_retries(monkeypatch):
    slept = []

    async def fake_sleep(seconds):
        slept.append(seconds)

    monkeypatch.setattr(tg_retry.asyncio, "sleep", fake_sleep)
    calls = {"n": 0}

    async def send():
        calls["n"] += 1
        if calls["n"] == 1:
            raise _flood(16)
        return "sent"

    assert asyncio.run(tg_retry.with_flood_retry(send)) == "sent"
    assert slept == [17]


def test_gives_up_on_long_wait(monkeypatch):
    async def send():
        raise _flood(600)

    with pytest.raises(TelegramRetryAfter):
        asyncio.run(tg_retry.with_flood_retry(send))


def test_gives_up_after_attempts(monkeypatch):
    async def fake_sleep(_seconds):
        return None

    monkeypatch.setattr(tg_retry.asyncio, "sleep", fake_sleep)

    async def send():
        raise _flood(1)

    with pytest.raises(TelegramRetryAfter):
        asyncio.run(tg_retry.with_flood_retry(send))

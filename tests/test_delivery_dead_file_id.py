"""Самолечение выдачи при мёртвом file_id.

file_id принадлежит боту, который загрузил файл. При переезде на нового бота все
7231 идентификатора в базе стали чужими, а архивных копий у каталога нет — трек
можно вернуть только повторной загрузкой из источника.
"""
from aiogram.exceptions import TelegramBadRequest

from app.db.models import Track, User
from app.handlers.delivery import send_track_audio


class DeadFileIdBot:
    """Telegram отвечает так, когда file_id выдан другим ботом."""

    def __init__(self):
        self.calls = 0

    async def send_audio(self, chat_id, audio, **kwargs):
        self.calls += 1
        raise TelegramBadRequest(method=None, message="Bad Request: wrong file identifier")


async def test_dead_file_id_is_cleared_and_repair_is_scheduled(session, monkeypatch):
    scheduled = []
    monkeypatch.setattr(
        "app.tasks.search_fetch.repair_track.delay",
        lambda **kwargs: scheduled.append(kwargs),
    )
    user = User(telegram_id=1)
    track = Track(
        title="Fake ID", artist="Kizaru", duration=180, format="mp3",
        tg_file_id="file_id_of_the_old_bot", meta_synced=True,
    )
    session.add_all([user, track])
    await session.commit()

    message = await send_track_audio(DeadFileIdBot(), 42, session, user, track)

    assert message is None
    assert track.tg_file_id is None  # мёртвый id погашен, повторно им не бьёмся
    assert track.meta_synced is False
    assert scheduled == [{"track_id": track.id, "chat_id": 42}]


async def test_broker_outage_does_not_break_delivery(session, monkeypatch):
    """Без брокера отдача просто вернёт None — падать в лицо пользователю нельзя."""
    def explode(**kwargs):
        raise RuntimeError("брокер недоступен")

    monkeypatch.setattr("app.tasks.search_fetch.repair_track.delay", explode)
    user = User(telegram_id=2)
    track = Track(
        title="Секс", artist="Lida", duration=120, format="mp3",
        tg_file_id="dead", meta_synced=True,
    )
    session.add_all([user, track])
    await session.commit()

    assert await send_track_audio(DeadFileIdBot(), 7, session, user, track) is None
    assert track.tg_file_id is None

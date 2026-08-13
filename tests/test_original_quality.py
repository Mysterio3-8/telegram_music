"""Оригинальное качество (WAV/FLAC от автора) — пункт 1 спеки 13.08.

Главное, что здесь стережётся: человек НИКОГДА не остаётся без трека и никогда
не видит ошибку из-за оригинала. mp3 уходит первым и всегда; оригинал — бонус,
который может не случиться десятком способов.
"""
from dataclasses import asdict
from datetime import datetime, timedelta, timezone

import pytest

from app.config import settings
from app.db.models import Track, User
from app.services import original_audio
from app.services.original_audio import (
    HQ_NONE,
    HQ_READY,
    QUALITY_MP3,
    QUALITY_ORIGINAL,
    deliver_original,
    wants_original,
)
from app.services.soundcloud_api import _to_candidate
from app.services.track_lookup.ranking import Candidate


class _Document:
    def __init__(self, file_id: str) -> None:
        self.file_id = file_id


class _Sent:
    def __init__(self, file_id: str) -> None:
        self.document = _Document(file_id)


class FakeBot:
    """Считает отправки: по file_id (пересылка) и байтами (минт)."""

    def __init__(self) -> None:
        self.documents: list[tuple[int, object, str | None]] = []

    async def send_document(self, chat_id, document, caption=None):
        self.documents.append((chat_id, document, caption))
        return _Sent("minted-doc-id")


@pytest.fixture
def track() -> Track:
    return Track(
        id=1,
        title="Зеркало",
        artist="Кизару",
        duration=180,
        source_url="https://soundcloud.com/kizaru/zerkalo",
    )


def _user(**kwargs) -> User:
    defaults = {
        "id": 1,
        "telegram_id": 555,
        "audio_quality": QUALITY_ORIGINAL,
        "premium": True,
        # is_premium_active смотрит на срок, а не только на флаг: подписка,
        # у которой вышел срок, Premium-функций больше не открывает.
        # Время наивное (без зоны) — так его хранит вся база проекта.
        "premium_until": datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=30),
    }
    defaults.update(kwargs)
    return User(**defaults)


# --- признак доступности из выдачи -----------------------------------------


def _api_item(**extra) -> dict:
    item = {
        "permalink_url": "https://soundcloud.com/kizaru/zerkalo",
        "title": "Кизару - Зеркало",
        "duration": 180000,
        "user": {"username": "kizaru"},
    }
    item.update(extra)
    return item


def test_hq_available_requires_both_flags():
    """`downloadable` без остатка квоты — это отказ на скачивании, а не оригинал."""
    assert _to_candidate(_api_item(downloadable=True, has_downloads_left=True)).hq_available
    assert not _to_candidate(_api_item(downloadable=True, has_downloads_left=False)).hq_available
    assert not _to_candidate(_api_item(downloadable=False, has_downloads_left=True)).hq_available
    assert not _to_candidate(_api_item()).hq_available


def test_candidate_from_old_cache_has_no_hq():
    """Выдача, закэшированная в Redis прошлой версией кода, поля не содержит.
    Кандидат обязан собираться из неё без падения — иначе после деплоя поиск
    ломается ровно на три часа, пока кэш не протухнет."""
    old_row = asdict(Candidate(source="soundcloud", url="u", title="t", duration=1))
    del old_row["hq_available"]
    assert Candidate(**old_row).hq_available is False


# --- кто имеет право ---------------------------------------------------------


def test_wants_original_only_for_paying_users():
    assert wants_original(_user())
    assert not wants_original(_user(premium=False, premium_until=None))
    assert not wants_original(_user(audio_quality="mp3"))


# --- выдача -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ready_original_goes_by_file_id(session, track, monkeypatch):
    """Уже заминченный оригинал уходит мгновенно — в сеть не ходим вовсе."""
    track.hq_file_id = "doc-42"
    track.hq_format = "flac"
    track.hq_size = 30 * 1024 * 1024
    track.hq_status = HQ_READY
    session.add(track)
    await session.commit()

    called = False

    async def _never(url):
        nonlocal called
        called = True
        return b"", ""

    monkeypatch.setattr(original_audio, "_download_original", _never)
    bot = FakeBot()

    assert await deliver_original(session, bot, track, chat_id=777) is True
    assert not called
    assert bot.documents[0][0] == 777
    assert bot.documents[0][1] == "doc-42"


@pytest.mark.asyncio
async def test_missing_original_is_remembered(session, track, monkeypatch):
    """Автор не разрешил скачивание — помечаем трек и больше не пробуем."""
    session.add(track)
    await session.commit()

    async def _empty(url):
        return b"", ""

    monkeypatch.setattr(original_audio, "_download_original", _empty)
    bot = FakeBot()

    assert await deliver_original(session, bot, track, 777, hq_available=True) is False
    assert track.hq_status == HQ_NONE
    assert bot.documents == []  # человеку ни слова: mp3 он уже получил


@pytest.mark.asyncio
async def test_network_error_does_not_mark_track(session, track, monkeypatch):
    """Сбой сети временный. Пометив трек, мы бы навсегда лишили оригинала всех."""
    session.add(track)
    await session.commit()

    async def _broken(url):
        return None, ""

    monkeypatch.setattr(original_audio, "_download_original", _broken)

    assert await deliver_original(session, FakeBot(), track, 777, hq_available=True) is False
    assert track.hq_status is None


@pytest.mark.asyncio
async def test_oversized_original_falls_back_silently(session, track, monkeypatch):
    """Лимит Bot API 50 МБ: пятиминутный WAV не влезает. Это не ошибка человека."""
    monkeypatch.setattr(settings, "original_max_size_mb", 1)

    session.add(track)
    await session.commit()

    async def _huge(url):
        return b"x" * (2 * 1024 * 1024), "wav"

    monkeypatch.setattr(original_audio, "_download_original", _huge)
    bot = FakeBot()

    assert await deliver_original(session, bot, track, 777, hq_available=True) is False
    assert track.hq_status == HQ_NONE
    assert track.hq_file_id is None
    assert bot.documents == []


@pytest.mark.asyncio
async def test_original_is_minted_then_sent(session, track, monkeypatch):
    """Успешный путь: минт в архив, поля трека заполнены, файл ушёл человеку."""
    monkeypatch.setattr(settings, "telegram_archive_chat_id", -100500)

    session.add(track)
    await session.commit()

    async def _wav(url):
        return b"RIFF" + b"0" * 1024, "wav"

    monkeypatch.setattr(original_audio, "_download_original", _wav)
    bot = FakeBot()

    assert await deliver_original(session, bot, track, 777, hq_available=True) is True
    assert track.hq_status == HQ_READY
    assert track.hq_format == "wav"
    assert track.hq_file_id == "minted-doc-id"
    assert track.hq_size == 1028

    # Первый вызов — минт в архив байтами, второй — пересылка человеку по file_id
    assert bot.documents[0][0] == -100500
    assert bot.documents[1][0] == 777
    assert bot.documents[1][1] == "minted-doc-id"
    assert "WAV" in bot.documents[1][2]


@pytest.mark.asyncio
async def test_no_network_call_when_source_says_no(session, track, monkeypatch):
    """Выдача сказала «оригинала нет» — не тратим ни очередь, ни закачку."""
    session.add(track)
    await session.commit()

    async def _never(url):
        raise AssertionError("не должны ходить в сеть")

    monkeypatch.setattr(original_audio, "_download_original", _never)

    assert await deliver_original(session, FakeBot(), track, 777, hq_available=False) is False
    assert track.hq_status is None  # это свойство ЭТОГО аплоада, а не трека


# --- экран настроек ------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_quality_falls_back_to_mp3(session):
    """В callback_data приходит что угодно. Молча выдать оригинал по мусорному
    значению — значит раздать Premium-функцию всем подряд."""
    from app.services.users import set_audio_quality

    user = _user()
    session.add(user)
    await session.commit()

    assert await set_audio_quality(session, user, "wav-please") == QUALITY_MP3
    assert await set_audio_quality(session, user, QUALITY_ORIGINAL) == QUALITY_ORIGINAL
    assert user.audio_quality == QUALITY_ORIGINAL


def test_quality_keyboard_marks_current_choice():
    from app.keyboards.settings import quality_keyboard

    texts = [row[0].text for row in quality_keyboard(QUALITY_ORIGINAL, "ru").inline_keyboard]
    assert "✅" in texts[1] and "✅" not in texts[0]

    texts = [row[0].text for row in quality_keyboard(QUALITY_MP3, "ru").inline_keyboard]
    assert "✅" in texts[0] and "✅" not in texts[1]


@pytest.mark.asyncio
async def test_youtube_track_has_no_original(session, monkeypatch):
    """YouTube исходников не отдаёт — там всегда перекодированный поток."""
    track = Track(
        id=2, title="t", artist="a", duration=100,
        source_url="https://www.youtube.com/watch?v=abcdefghijk",
    )
    session.add(track)
    await session.commit()

    async def _never(url):
        raise AssertionError("не должны ходить в сеть")

    monkeypatch.setattr(original_audio, "_download_original", _never)

    assert await deliver_original(session, FakeBot(), track, 777, hq_available=True) is False

"""Платное качество выдачи — пункт 1 спеки 13.08, переделанный по замеру.

Спека обещала оригинал автора (WAV/FLAC). Прогон на проде показал, что
SoundCloud отдаёт его у 6 треков из 601 — 1%, и ни одного у популярных
артистов. Зато 160 kbps AAC есть практически у всех, и он стал содержанием
платного режима; оригинал остался первой ступенью лестницы форматов.

Главное, что здесь стережётся: человек НИКОГДА не остаётся без трека и никогда
не видит ошибку из-за качества. Не вышло — уходит обычный mp3.
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
    QUALITY_BEST,
    QUALITY_MP3,
    deliver_best_quality,
    wants_best_quality,
)
from app.services.soundcloud_api import _to_candidate
from app.services.track_lookup.ranking import Candidate


class _File:
    def __init__(self, file_id: str) -> None:
        self.file_id = file_id


class _SentDocument:
    def __init__(self, file_id: str) -> None:
        self.document = _File(file_id)
        self.audio = None


class _SentAudio:
    def __init__(self, file_id: str) -> None:
        self.audio = _File(file_id)
        self.document = None


class FakeBot:
    """Пишет, чем и куда отправляли: (метод, чат, что, подпись)."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, int, object, str | None]] = []

    async def send_document(self, chat_id, document, caption=None):
        self.sent.append(("document", chat_id, document, caption))
        return _SentDocument("minted-doc-id")

    async def send_audio(self, chat_id, audio, caption=None, **kwargs):
        self.sent.append(("audio", chat_id, audio, caption))
        return _SentAudio("minted-audio-id")


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
        "audio_quality": QUALITY_BEST,
        "premium": True,
        # is_premium_active смотрит на срок, а не только на флаг: подписка,
        # у которой вышел срок, Premium-функций больше не открывает.
        # Время наивное (без зоны) — так его хранит вся база проекта.
        "premium_until": datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=30),
    }
    defaults.update(kwargs)
    return User(**defaults)


# --- признак оригинала из выдачи ---------------------------------------------


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
    """`downloadable` без остатка квоты — отказ на скачивании, а не оригинал."""
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


def test_wants_best_quality_only_for_paying_users():
    assert wants_best_quality(_user())
    assert not wants_best_quality(_user(premium=False, premium_until=None))
    assert not wants_best_quality(_user(audio_quality=QUALITY_MP3))


# --- выдача -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ready_file_goes_by_file_id(session, track, monkeypatch):
    """Уже заминченное качество уходит мгновенно — в сеть не ходим вовсе."""
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

    monkeypatch.setattr(original_audio, "_download_best", _never)
    bot = FakeBot()

    assert await deliver_best_quality(session, bot, track, chat_id=777) is True
    assert not called
    assert bot.sent[0][:3] == ("document", 777, "doc-42")


@pytest.mark.asyncio
async def test_m4a_goes_as_audio_not_document(session, track, monkeypatch):
    """160 kbps AAC играет в плеере Telegram — слать его вложением значит
    превратить обычный трек в молчаливый файл."""
    monkeypatch.setattr(settings, "telegram_archive_chat_id", -100500)
    session.add(track)
    await session.commit()

    async def _aac(url):
        return b"\x00" * 2048, "m4a"

    monkeypatch.setattr(original_audio, "_download_best", _aac)
    bot = FakeBot()

    assert await deliver_best_quality(session, bot, track, 777) is True
    assert track.hq_format == "m4a"
    assert track.hq_file_id == "minted-audio-id"
    assert [row[0] for row in bot.sent] == ["audio", "audio"]  # минт и выдача
    assert bot.sent[0][1] == -100500
    assert bot.sent[1][1] == 777


@pytest.mark.asyncio
async def test_lossless_goes_as_document(session, track, monkeypatch):
    """WAV в плеере Telegram не играет — только вложением."""
    monkeypatch.setattr(settings, "telegram_archive_chat_id", -100500)
    session.add(track)
    await session.commit()

    async def _wav(url):
        return b"RIFF" + b"0" * 1024, "wav"

    monkeypatch.setattr(original_audio, "_download_best", _wav)
    bot = FakeBot()

    assert await deliver_best_quality(session, bot, track, 777) is True
    assert track.hq_status == HQ_READY
    assert track.hq_size == 1028
    assert [row[0] for row in bot.sent] == ["document", "document"]
    assert "WAV" in bot.sent[1][3]


@pytest.mark.asyncio
async def test_nothing_to_download_is_remembered(session, track, monkeypatch):
    """Источнику нечего отдать (DRM, приватный трек) — помечаем и не повторяем."""
    session.add(track)
    await session.commit()

    async def _empty(url):
        return b"", ""

    monkeypatch.setattr(original_audio, "_download_best", _empty)
    bot = FakeBot()

    assert await deliver_best_quality(session, bot, track, 777) is False
    assert track.hq_status == HQ_NONE
    assert bot.sent == []  # ни слова человеку: следом ему уйдёт обычный mp3


@pytest.mark.asyncio
async def test_network_error_does_not_mark_track(session, track, monkeypatch):
    """Сбой сети временный. Пометив трек, мы бы лишили качества всех и навсегда."""
    session.add(track)
    await session.commit()

    async def _broken(url):
        return None, ""

    monkeypatch.setattr(original_audio, "_download_best", _broken)

    assert await deliver_best_quality(session, FakeBot(), track, 777) is False
    assert track.hq_status is None


@pytest.mark.asyncio
async def test_oversized_file_falls_back_silently(session, track, monkeypatch):
    """Лимит Bot API 50 МБ: пятиминутный WAV не влезает. Это не ошибка человека."""
    monkeypatch.setattr(settings, "original_max_size_mb", 1)
    session.add(track)
    await session.commit()

    async def _huge(url):
        return b"x" * (2 * 1024 * 1024), "wav"

    monkeypatch.setattr(original_audio, "_download_best", _huge)
    bot = FakeBot()

    assert await deliver_best_quality(session, bot, track, 777) is False
    assert track.hq_status == HQ_NONE
    assert track.hq_file_id is None
    assert bot.sent == []


@pytest.mark.asyncio
async def test_youtube_track_has_no_better_quality(session, monkeypatch):
    """У YouTube своей лестницы качества нет — там всегда перекодированный поток."""
    track = Track(
        id=2, title="t", artist="a", duration=100,
        source_url="https://www.youtube.com/watch?v=abcdefghijk",
    )
    session.add(track)
    await session.commit()

    async def _never(url):
        raise AssertionError("не должны ходить в сеть")

    monkeypatch.setattr(original_audio, "_download_best", _never)

    assert await deliver_best_quality(session, FakeBot(), track, 777) is False
    assert track.hq_status is None  # источник может смениться, приговор не выносим


# --- экран настроек ------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_quality_falls_back_to_mp3(session):
    """В callback_data приходит что угодно. Молча выдать платное качество по
    мусорному значению — значит раздать Premium-функцию всем подряд."""
    from app.services.users import set_audio_quality

    user = _user()
    session.add(user)
    await session.commit()

    assert await set_audio_quality(session, user, "wav-please") == QUALITY_MP3
    assert await set_audio_quality(session, user, QUALITY_BEST) == QUALITY_BEST
    assert user.audio_quality == QUALITY_BEST


def test_quality_keyboard_marks_current_choice():
    from app.keyboards.settings import quality_keyboard

    texts = [row[0].text for row in quality_keyboard(QUALITY_BEST, "ru").inline_keyboard]
    assert "✅" in texts[1] and "✅" not in texts[0]

    texts = [row[0].text for row in quality_keyboard(QUALITY_MP3, "ru").inline_keyboard]
    assert "✅" in texts[0] and "✅" not in texts[1]


def test_settings_keyboard_keeps_back_last():
    """«Назад» обязана оставаться последней: переключатель обложки вставляется
    между ней и качеством, и лёгкая ошибка здесь загоняет выход в середину."""
    from app.keyboards.settings import settings_keyboard

    rows = settings_keyboard(QUALITY_MP3, cover_as_file=False, lang="ru").inline_keyboard
    assert rows[-1][0].callback_data == "menu:main"
    assert rows[-2][0].callback_data == "set:cover"


@pytest.mark.asyncio
async def test_cover_toggle_flips_and_persists(session):
    from app.services.users import toggle_cover_as_file

    user = _user(audio_quality=QUALITY_MP3)
    session.add(user)
    await session.commit()

    assert await toggle_cover_as_file(session, user) is True
    assert user.cover_as_file is True
    assert await toggle_cover_as_file(session, user) is False


@pytest.mark.asyncio
async def test_cover_not_sent_when_disabled(session, track):
    """Выключено — ни сети, ни лишнего сообщения."""
    from app.handlers.delivery import _maybe_send_cover

    track.cover_url = "https://cdn/cover.jpg"
    user = _user(cover_as_file=False)
    bot = FakeBot()

    await _maybe_send_cover(bot, 777, user, track)
    assert bot.sent == []


@pytest.mark.asyncio
async def test_cover_sent_as_document(session, track, monkeypatch):
    """Документом, а не фото: Telegram пережимает фотографии, а смысл опции —
    получить картинку целиком."""
    from app.handlers import delivery
    from app.services.youtube import downloader

    track.cover_url = "https://cdn/cover.jpg"
    user = _user(cover_as_file=True)
    monkeypatch.setattr(downloader, "fetch_thumbnail", lambda url: b"JPEGDATA")
    bot = FakeBot()

    await delivery._maybe_send_cover(bot, 777, user, track)
    assert [row[0] for row in bot.sent] == ["document"]
    assert bot.sent[0][1] == 777


@pytest.mark.asyncio
async def test_cover_failure_never_breaks_delivery(session, track, monkeypatch):
    """Трек человек уже получил. Падать из-за картинки нельзя."""
    from app.handlers import delivery
    from app.services.youtube import downloader

    track.cover_url = "https://cdn/cover.jpg"
    user = _user(cover_as_file=True)

    def _boom(url):
        raise RuntimeError("сеть отвалилась")

    monkeypatch.setattr(downloader, "fetch_thumbnail", _boom)

    await delivery._maybe_send_cover(FakeBot(), 777, user, track)  # не должно бросить

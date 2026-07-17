from app.config import settings
from app.handlers.inline import _open_bot_keyboard


def test_open_bot_keyboard_uses_sender_referral_link(monkeypatch):
    monkeypatch.setattr(settings, "bot_username", "tgram_music_bot")

    keyboard = _open_bot_keyboard(777)

    button = keyboard.inline_keyboard[0][0]
    assert button.text == "🎧 Слушать в TG Music"
    # приглашённый засчитывается отправителю трека
    assert button.url == "https://t.me/tgram_music_bot?start=ref_777"


def test_open_bot_keyboard_none_without_bot_username(monkeypatch):
    monkeypatch.setattr(settings, "bot_username", "")

    # без BOT_USERNAME ссылку не построить — выдача просто идёт без кнопки
    assert _open_bot_keyboard(777) is None

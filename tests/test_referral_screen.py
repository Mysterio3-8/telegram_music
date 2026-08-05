"""Реферальный экран бота. Пороги берутся из gamification, а не дублируются —
именно поэтому важно проверить, что текст строится из настоящих данных.
"""
from app.config import settings
from app.db.models import User
from app.handlers.referral import (
    _days_word,
    _friends_word,
    _reward_text,
    _rewards_block,
    build_referral_text,
)
from app.keyboards.referral import referral_keyboard, share_url
from app.services.gamification import LIFETIME_DAYS, REFERRAL_MILESTONES


def test_friends_word_matches_russian_counting():
    assert _friends_word(1) == "друг"
    assert _friends_word(2) == "друга"
    assert _friends_word(5) == "друзей"
    assert _friends_word(11) == "друзей"  # 11 не «друг», хотя оканчивается на 1
    assert _friends_word(21) == "друг"


def test_days_word_matches_russian_counting():
    assert _days_word(1) == "день"
    assert _days_word(3) == "дня"
    assert _days_word(14) == "дней"


def test_rewards_show_reached_and_upcoming():
    block = _rewards_block(invited=3)
    assert "✅" in block and "🎁" in block
    # достигнутый порог 1 отмечен галочкой, ближайший непройденный 5 — подарком
    assert "✅ 1 друг" in block
    assert "🎁 5 друзей" in block


def test_rewards_for_newcomer_have_no_checkmarks():
    assert "✅" not in _rewards_block(invited=0)


def test_first_milestone_is_one_day():
    """«Один друг — один день Premium» из текста должно совпадать с порогом."""
    assert REFERRAL_MILESTONES[0] == (1, 1)


def test_lifetime_milestone_reads_as_forever():
    """36500 дней человеку показывать нельзя — верхний порог пишется словом."""
    assert _reward_text(LIFETIME_DAYS) == "Premium навсегда"
    assert REFERRAL_MILESTONES[-1] == (5000, LIFETIME_DAYS)


async def test_referral_text_contains_link_and_counters(session):
    user = User(telegram_id=777, first_name="Ivan")
    session.add(user)
    await session.commit()

    text = await build_referral_text(session, user)
    assert f"t.me/{settings.bot_username}" in text
    assert "start=ref_777" in text  # ссылка персональная
    assert "Приглашено: <b>0</b>" in text


def test_share_button_carries_the_link():
    markup = referral_keyboard("https://t.me/bot?start=1")
    share = markup.inline_keyboard[0][0]
    assert share.url.startswith("https://t.me/share/url?")
    assert "start%3D1" in share.url  # ссылка ушла в параметр закодированной
    assert share.url.count("http") >= 2  # и сама ссылка, и адрес шеринга


def test_share_url_escapes_the_link():
    assert " " not in share_url("https://t.me/bot?start=1")

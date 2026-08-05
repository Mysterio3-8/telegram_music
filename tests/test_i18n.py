"""Мультиязычность: цепочка запасных языков и выбор пользователя.

Главное, что проверяем, — непереведённый язык не показывает человеку ключи и не
роняет экран, а падает на английский.
"""
from app.db.models import User
from app.i18n import (
    DEFAULT_LANGUAGE,
    LANGUAGES,
    TRANSLATIONS,
    is_translated,
    normalize_language,
    t,
    tracks_word,
)
from app.services.users import set_user_language, user_language


def test_every_language_has_a_dictionary():
    """Язык в списке без словаря уронил бы t() — пусть даже пустым, но он должен быть."""
    for item in LANGUAGES:
        assert item.code in TRANSLATIONS


def test_russian_and_english_are_translated():
    assert is_translated("ru")
    assert is_translated("en")


def test_stub_languages_fall_back_to_english():
    for code in ("es", "de", "fr", "pt", "tr"):
        assert not is_translated(code)
        assert t("menu.referral", code) == t("menu.referral", "en")


def test_unknown_key_returns_itself_instead_of_crashing():
    assert t("no.such.key", "ru") == "no.such.key"


def test_placeholders_are_filled():
    assert "199" in t("menu.premium", "ru", price=199)
    assert "199" in t("menu.premium", "en", price=199)


def test_normalize_language_handles_telegram_codes():
    assert normalize_language("en-US") == "en"
    assert normalize_language("pt-BR") == "pt"
    assert normalize_language("zh-Hans") == DEFAULT_LANGUAGE  # не поддерживаем
    assert normalize_language(None) == DEFAULT_LANGUAGE


def test_tracks_word_russian_plurals():
    assert tracks_word(1, "ru") == "трек"
    assert tracks_word(3, "ru") == "трека"
    assert tracks_word(11, "ru") == "треков"  # 11 не «трек», хотя оканчивается на 1
    assert tracks_word(21, "ru") == "трек"


def test_tracks_word_english_plurals():
    assert tracks_word(1, "en") == "track"
    assert tracks_word(2, "en") == "tracks"


async def test_explicit_choice_wins_over_telegram_profile(session):
    """users.language перезаписывается на каждом /start, поэтому выбор человека
    живёт отдельно — иначе он бы затирался кодом из профиля."""
    user = User(telegram_id=1, language="ru")
    session.add(user)
    await session.commit()
    assert user_language(user) == "ru"

    await set_user_language(session, user, "en")
    assert user_language(user) == "en"

    user.language = "ru"  # профиль Telegram обновился — выбор остаётся
    await session.commit()
    assert user_language(user) == "en"


async def test_unsupported_choice_falls_back_to_default(session):
    user = User(telegram_id=2)
    session.add(user)
    await session.commit()
    assert await set_user_language(session, user, "klingon") == DEFAULT_LANGUAGE

"""Мультиязычность: цепочка запасных языков и выбор пользователя.

Главное, что проверяем, — непереведённый язык не показывает человеку ключи и не
роняет экран, а падает на английский.
"""
from app.db.models import User
from app.i18n import (
    DEFAULT_LANGUAGE,
    FALLBACK_LANGUAGE,
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


def test_every_language_is_translated():
    for item in LANGUAGES:
        assert is_translated(item.code), f"{item.code} без перевода"


def test_no_language_lost_keys():
    """Ключи заводятся в русском; язык, отставший от него, молча покажет чужой текст."""
    source = set(TRANSLATIONS["ru"])
    for item in LANGUAGES:
        if item.code == "ru":
            continue
        missing = source - set(TRANSLATIONS[item.code])
        # формы множественного числа: русскому нужны три, остальным хватает двух
        missing = {key for key in missing if not key.endswith(".few")}
        assert not missing, f"{item.code}: не переведено {sorted(missing)}"


def test_no_language_has_extra_keys():
    """Лишний ключ — след переименования: строка мертва и никогда не покажется."""
    source = set(TRANSLATIONS["ru"])
    for item in LANGUAGES:
        extra = set(TRANSLATIONS[item.code]) - source
        assert not extra, f"{item.code}: ключей нет в русском — {sorted(extra)}"


def test_unknown_key_returns_itself_instead_of_crashing():
    assert t("no.such.key", "ru") == "no.such.key"


def test_placeholders_are_filled():
    assert "199" in t("menu.premium", "ru", price=199)
    assert "199" in t("menu.premium", "en", price=199)


def test_normalize_language_handles_telegram_codes():
    assert normalize_language("en-US") == "en"
    assert normalize_language("pt-BR") == "pt"
    assert normalize_language(None) == DEFAULT_LANGUAGE  # Telegram не сказал — ядро аудитории


def test_unknown_language_goes_to_english_not_russian():
    """Японцу или поляку русский интерфейс поможет меньше, чем международный."""
    for code in ("ja", "zh-Hans", "pl", "hi", "ar"):
        assert normalize_language(code) == FALLBACK_LANGUAGE


def test_post_soviet_languages_go_to_russian():
    """Своего перевода у них нет, но русский тут вероятнее английского."""
    for code in ("uk", "be", "kk", "uz", "hy", "ka"):
        assert normalize_language(code) == DEFAULT_LANGUAGE


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


async def test_first_screen_after_start_is_in_device_language(session):
    """Гейт подписки — самый первый экран новичка, раньше кабинета. Он был
    захардкожен по-русски, и англоязычный человек утыкался в русский текст."""
    from app.handlers.start import build_cabinet_text
    from app.keyboards.subscription import subscription_gate_keyboard

    user = User(telegram_id=4, first_name="John", language="en-GB")
    session.add(user)
    await session.commit()
    lang = user_language(user)

    assert "subscribe to our channels" in t("gate.text", lang)
    check_button = subscription_gate_keyboard([], lang).inline_keyboard[-1][0]
    assert check_button.text == t("gate.check", "en")

    cabinet = await build_cabinet_text(session, user)
    assert "Hi, <b>John</b>" in cabinet
    assert "In your library" in cabinet


async def test_unsupported_choice_falls_back_instead_of_saving_garbage(session):
    user = User(telegram_id=2)
    session.add(user)
    await session.commit()
    assert await set_user_language(session, user, "klingon") == FALLBACK_LANGUAGE


async def test_device_language_applies_without_explicit_choice(session):
    """Запрос владельца: язык определяется устройством сразу на /start.

    ui_language сознательно не заполняем автоопределением — иначе человек сменит
    язык телефона, а бот продолжит говорить на старом."""
    user = User(telegram_id=3, language="en-US")
    session.add(user)
    await session.commit()

    assert user.ui_language is None
    assert user_language(user) == "en"

    user.language = "de-DE"  # сменил язык телефона — бот едет следом
    await session.commit()
    assert user_language(user) == "de"

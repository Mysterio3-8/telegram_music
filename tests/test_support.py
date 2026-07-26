from app.services.support import (
    CATEGORIES,
    rate_limited,
    text_too_short,
    ticket_header,
)


def test_text_too_short():
    assert text_too_short("баг") is True
    assert text_too_short("   ") is True
    assert text_too_short("Не работает загрузка треков вторые сутки") is False


def test_rate_limited_after_three():
    uid = 777
    t = 1000.0
    assert rate_limited(uid, now=t) is False
    assert rate_limited(uid, now=t + 1) is False
    assert rate_limited(uid, now=t + 2) is False
    assert rate_limited(uid, now=t + 3) is True  # 4-е за окно — стоп
    # спустя окно снова можно
    assert rate_limited(uid, now=t + 4000) is False


def test_categories_present():
    assert set(CATEGORIES.values()) == {"Жалоба", "Отзыв", "Предложение"}


def test_ticket_header():
    class U:
        id = 42
        username = "ivan"
        full_name = "Иван П."

    header = ticket_header("Жалоба", U())
    assert "Жалоба" in header
    assert "@ivan" in header
    assert "42" in header

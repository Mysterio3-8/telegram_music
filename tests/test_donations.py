"""Донаты: суммы, рейтинг, идемпотентность и возвраты.

Отдельный акцент на защите оплаты — это то, что владелец просил проверить
особо: сумма приходит из callback_data, то есть от клиента, а повторное
уведомление ЮKassa не должно удваивать вклад в рейтинге.
"""
import pytest

from app.db.models import Donation, User
from app.services.donations import (
    MAX_AMOUNT_RUB,
    MIN_AMOUNT_RUB,
    display_name,
    donations_summary,
    is_allowed_amount,
    mark_refunded,
    parse_amount,
    record_donation,
    top_sponsors,
    user_rank,
    user_total,
)


async def _user(session, telegram_id: int, username: str | None = None) -> User:
    user = User(telegram_id=telegram_id, username=username)
    session.add(user)
    await session.flush()
    return user


# --- суммы ------------------------------------------------------------------

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("300", 300),
        ("  49  ", 49),
        ("1 000", 1000),
        ("1_000", 1000),
        ("500₽", 500),
        (str(MIN_AMOUNT_RUB), MIN_AMOUNT_RUB),
        (str(MAX_AMOUNT_RUB), MAX_AMOUNT_RUB),
    ],
)
def test_parse_amount_accepts_sane_input(raw, expected):
    assert parse_amount(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "abc",
        "-100",           # минус: платёж на отрицательную сумму
        "0",
        str(MIN_AMOUNT_RUB - 1),
        str(MAX_AMOUNT_RUB + 1),
        "49.5",           # копейки не поддерживаем сознательно
        "1e5",            # float() принял бы это как 100000
        "inf",            # и это тоже — а дальше оно уехало бы в кассу
        "nan",
        "٤٩",             # арабские цифры: isdigit() их пропускает
        "²",              # isdigit() истинен, а int() падает с ValueError
    ],
)
def test_parse_amount_rejects_junk(raw):
    assert parse_amount(raw) is None


def test_allowed_amount_guards_callback_data():
    # callback_data приходит от клиента и подделывается — на кнопку не полагаемся.
    assert is_allowed_amount(49)
    assert is_allowed_amount(777)
    assert not is_allowed_amount(1)
    assert not is_allowed_amount(0)
    assert not is_allowed_amount(-500)
    assert not is_allowed_amount(MAX_AMOUNT_RUB + 1)


# --- запись и идемпотентность ----------------------------------------------

@pytest.mark.asyncio
async def test_record_donation_is_idempotent(session):
    user = await _user(session, 1)
    first = await record_donation(session, user.id, 249, "pay-1")
    assert first is not None
    # Повтор того же payment_id — ЮKassa ретраит уведомление, пока не получит 200.
    again = await record_donation(session, user.id, 249, "pay-1")
    assert again is None
    assert await user_total(session, user.id) == 249


@pytest.mark.asyncio
async def test_totals_sum_across_donations(session):
    user = await _user(session, 1)
    await record_donation(session, user.id, 100, "p1")
    await record_donation(session, user.id, 149, "p2")
    assert await user_total(session, user.id) == 249


# --- возвраты ---------------------------------------------------------------

@pytest.mark.asyncio
async def test_refund_removes_donation_from_rating(session):
    rich = await _user(session, 1, "rich")
    honest = await _user(session, 2, "honest")
    await record_donation(session, rich.id, 50_000, "cheat")
    await record_donation(session, honest.id, 499, "fair")

    assert (await top_sponsors(session))[0][0].id == rich.id

    # Чарджбэк: деньги вернулись, место в топе оставаться не должно.
    assert await mark_refunded(session, "cheat") is True
    rows = await top_sponsors(session)
    assert [user.id for user, _ in rows] == [honest.id]
    assert await user_total(session, rich.id) == 0


@pytest.mark.asyncio
async def test_refund_is_idempotent_and_tolerates_unknown(session):
    user = await _user(session, 1)
    await record_donation(session, user.id, 100, "p1")
    assert await mark_refunded(session, "p1") is True
    first_time = (await session.get(Donation, 1)).refunded_at
    assert await mark_refunded(session, "p1") is True
    assert (await session.get(Donation, 1)).refunded_at == first_time
    # Возврат по чужому платежу (например, за Premium) не должен ничего ломать.
    assert await mark_refunded(session, "unknown") is False


# --- рейтинг ----------------------------------------------------------------

@pytest.mark.asyncio
async def test_top_is_ordered_and_limited(session):
    for index in range(30):
        user = await _user(session, 100 + index, f"u{index}")
        await record_donation(session, user.id, (index + 1) * 10, f"p{index}")
    rows = await top_sponsors(session)
    assert len(rows) == 25, "показываем не больше 25 человек"
    amounts = [amount for _, amount in rows]
    assert amounts == sorted(amounts, reverse=True)
    assert amounts[0] == 300


@pytest.mark.asyncio
async def test_zero_and_refunded_are_hidden(session):
    zero = await _user(session, 1, "zero")
    refunded = await _user(session, 2, "refunded")
    real = await _user(session, 3, "real")
    await record_donation(session, zero.id, 0, "p0")
    await record_donation(session, refunded.id, 500, "p1")
    await mark_refunded(session, "p1")
    await record_donation(session, real.id, 49, "p2")

    rows = await top_sponsors(session)
    assert [user.id for user, _ in rows] == [real.id]


@pytest.mark.asyncio
async def test_rank_counts_everyone_not_just_visible_top(session):
    for index in range(30):
        user = await _user(session, 100 + index, f"u{index}")
        await record_donation(session, user.id, (30 - index) * 10, f"p{index}")
    # Первый донатер дал больше всех.
    top_user = (await top_sponsors(session))[0][0]
    assert await user_rank(session, top_user.id) == 1

    # Последний — 30-й, и он должен узнать своё место, хотя в списке его нет.
    last = await session.get(User, 30)
    assert await user_rank(session, last.id) == 30


@pytest.mark.asyncio
async def test_rank_is_none_without_donations(session):
    user = await _user(session, 1)
    assert await user_rank(session, user.id) is None


# --- подпись в рейтинге -----------------------------------------------------

@pytest.mark.asyncio
async def test_display_name_uses_username_then_stable_number(session):
    named = await _user(session, 1, "ivan")
    faceless = await _user(session, 2)
    assert display_name(named) == "@ivan"
    # Без юзернейма — обезличенно, но стабильно между заходами.
    assert display_name(faceless) == f"Спонсор #{faceless.id}"
    assert display_name(faceless) == display_name(faceless)


@pytest.mark.asyncio
async def test_display_name_never_uses_profile_name(session):
    """Имя из профиля человек пишет себе сам — в публичный список оно не идёт."""
    user = await _user(session, 1)
    user.first_name = "<b>КУПИ КВАРТИРУ</b> @spam"
    await session.flush()
    assert "КУПИ" not in display_name(user)


# --- сводка для админки -----------------------------------------------------

@pytest.mark.asyncio
async def test_summary_excludes_refunded(session):
    user = await _user(session, 1)
    await record_donation(session, user.id, 100, "p1")
    await record_donation(session, user.id, 200, "p2")
    await mark_refunded(session, "p2")
    assert await donations_summary(session) == (100, 1)

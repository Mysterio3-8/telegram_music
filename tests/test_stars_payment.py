"""Telegram Stars рядом с ЮKassa — пункт 2 спеки 13.08.

Порядок внутри пункта жёсткий: сначала приём Stars, потом партнёрская программа
Telegram. Она даёт 20% с покупок приглашённого, но работает ТОЛЬКО с оплатой
через Stars — со сторонним эквайрингом её включить нельзя.
"""
import pytest

from app.config import settings
from app.db.models import User
from app.handlers.premium import PAYLOAD_CARD, PAYLOAD_STARS, _months_from
from app.keyboards.premium import payment_method_keyboard, premium_keyboard
from app.services.premium import (
    FOREVER_MONTHS,
    PREMIUM_PLAN_DISCOUNTS,
    plan_price_rub,
    plan_price_stars,
)
from app.services.revenue import collect_revenue, record_payment


def test_stars_price_follows_the_same_discount_ladder():
    """Скидка за срок одинакова в обеих валютах. Разойдись они — годовой тариф
    оказался бы выгоден в рублях и невыгоден в звёздах, и человек поймал бы нас
    на несоответствии прямо на экране выбора."""
    for months, discount in PREMIUM_PLAN_DISCOUNTS.items():
        expected = settings.premium_price_stars * months * (100 - discount) // 100
        assert plan_price_stars(months) == expected
        # та же скидка, что и в рублях
        assert plan_price_rub(months) == settings.premium_price_rub * months * (100 - discount) // 100


def test_forever_plan_has_its_own_star_price():
    """«Навсегда» — фиксированная цена, а не 1200 месяцев по прайсу."""
    assert plan_price_stars(FOREVER_MONTHS) == settings.premium_forever_price_stars


def test_stars_price_never_drops_to_zero():
    """Счёт на 0 звёзд Telegram не примет. При любой скидке остаётся минимум 1."""
    assert plan_price_stars(1) >= 1
    assert plan_price_stars(12) >= 1


# --- разбор callback_data ------------------------------------------------------


def test_months_from_callback():
    assert _months_from("prem:stars:12") == 12
    assert _months_from("prem:stars:3") == 3
    # мусор и отсутствие срока — месяц, а не падение
    assert _months_from("prem:stars") == 1
    assert _months_from("prem:stars:abc") == 1
    assert _months_from("prem:stars:99") == 1  # несуществующий тариф


def test_pre_checkout_accepts_both_payloads():
    """Счёт без срока (`premium_stars`) выставлял код до 14.08. Он мог быть
    выписан до деплоя и оплачен после — отклонить его значит взять деньги и не
    дать подписку."""
    for payload in (PAYLOAD_STARS, f"{PAYLOAD_STARS}:12", f"{PAYLOAD_CARD}:3"):
        assert payload.split(":")[0] in (PAYLOAD_STARS, PAYLOAD_CARD)
    assert "hack".split(":")[0] not in (PAYLOAD_STARS, PAYLOAD_CARD)


# --- клавиатуры ----------------------------------------------------------------


def test_plan_buttons_lead_to_method_choice():
    rows = premium_keyboard(card_available=False, yookassa_available=True).inline_keyboard
    targets = [row[0].callback_data for row in rows[:-1]]
    assert targets == ["prem:plan:1", "prem:plan:3", "prem:plan:6", "prem:plan:12"]


def test_stars_offered_even_without_rub_provider():
    """Ни ЮKassa, ни токена карты — Stars остаются рабочим способом, а не
    пустым экраном. Раньше без рублёвого провайдера кнопок не было вовсе."""
    rows = payment_method_keyboard(1, card_available=False, yookassa_available=False)
    targets = [row[0].callback_data for row in rows.inline_keyboard]
    assert targets == ["prem:stars:1", "menu:premium"]


def test_both_methods_when_yookassa_configured():
    rows = payment_method_keyboard(12, card_available=False, yookassa_available=True)
    targets = [row[0].callback_data for row in rows.inline_keyboard]
    assert targets == ["prem:stars:12", "prem:yookassa:12", "menu:premium"]
    # срок доезжает до обеих кнопок: без него оплата года включала бы месяц
    assert all(":12" in target for target in targets[:2])


# --- учёт выручки ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_stars_revenue_counted_apart_from_rubles(session):
    """Складывать звёзды с рублями нельзя: курс плавающий, Telegram удерживает
    свою долю. До этой правки звёздный платёж писался с amount_rub=0 и выглядел
    в отчёте как бесплатная подписка — сумма терялась целиком."""
    user = User(id=1, telegram_id=555)
    session.add(user)
    await session.commit()

    await record_payment(session, user.id, 29, "yookassa", "ch-1")
    await record_payment(session, user.id, 0, "stars", "ch-2", amount_stars=50)
    await record_payment(session, user.id, 0, "stars", "ch-3", amount_stars=540)

    stats = await collect_revenue(session)
    assert stats.total == 29  # рубли не раздуты звёздами
    assert stats.payments_total == 1
    assert stats.stars_total == 590
    assert stats.stars_payments == 2

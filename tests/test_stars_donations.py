"""Донаты в Telegram Stars.

Главное, что здесь стережётся: **донат звёздами никогда не выдаёт Premium**.
Оплата Premium звёздами и донат звёздами приходят одними и теми же апдейтами
(pre_checkout_query, successful_payment), и роутер Premium зарегистрирован
раньше. Без явного разведения по payload донат уехал бы в activate_premium —
то есть дарение молча превратилось бы в продажу.
"""
from contextlib import asynccontextmanager

import pytest
from aiogram import Bot, Dispatcher
from aiogram.types import Message, PreCheckoutQuery, Update
from sqlalchemy import func, select

from app.config import settings
from app.db.models import Donation, PremiumSubscription
from app.handlers import donate, premium
from app.keyboards.donate import donate_method_keyboard
from app.middlewares import is_payment_message
from app.middlewares.subscription import _is_exempt
from app.middlewares.throttling import ThrottlingMiddleware
from app.services import donations
from app.services.donations import (
    MAX_STARS_PER_INVOICE,
    parse_stars_payload,
    rub_for_stars,
    stars_for_rub,
    stars_payload,
)

TG_USER = {"id": 777, "is_bot": False, "first_name": "Payer", "username": "payer"}


@pytest.fixture
def stars_on(monkeypatch):
    monkeypatch.setattr(settings, "stars_rub_rate", 0.7, raising=False)


# --- пересчёт курса ---------------------------------------------------------

def test_stars_off_without_rate(monkeypatch):
    monkeypatch.setattr(settings, "stars_rub_rate", 0.0, raising=False)
    assert not donations.is_stars_configured()


@pytest.mark.parametrize("rub", [10, 49, 149, 249, 499, 1000, 6999])
def test_round_trip_never_loses_a_ruble(stars_on, rub):
    """🔴 70 * 0.7 = 48.99999999999999: голый int() записал бы в цель 48 ₽ за
    донат, выбранный на кнопке «49 ₽». Найдено при написании этого теста."""
    assert rub_for_stars(stars_for_rub(rub)) >= rub


def test_stars_rounded_up(stars_on):
    assert stars_for_rub(49) == 70
    assert stars_for_rub(50) == 72  # 71.43 → 72, а не 71


def test_amount_over_invoice_limit_is_not_offered_in_stars(stars_on):
    """🔴 Bot API не принимает счёт больше 10 000 ⭐. Обрезать до потолка нельзя:
    человек заплатил бы ~7 000 ₽, а в цель легли бы все 12 345. Такую сумму
    звёздами просто не предлагаем."""
    assert donations.can_pay_in_stars(7000)  # ровно 10 000 ⭐
    assert stars_for_rub(7000) == MAX_STARS_PER_INVOICE
    assert not donations.can_pay_in_stars(7001)
    with pytest.raises(ValueError):
        stars_for_rub(12345)


def test_cannot_pay_in_stars_when_off(monkeypatch):
    monkeypatch.setattr(settings, "stars_rub_rate", 0.0, raising=False)
    assert not donations.can_pay_in_stars(49)


def test_stars_for_rub_without_rate_is_loud(monkeypatch):
    monkeypatch.setattr(settings, "stars_rub_rate", 0.0, raising=False)
    with pytest.raises(ValueError):
        stars_for_rub(49)


# --- payload ------------------------------------------------------------------

def test_payload_roundtrip():
    assert parse_stars_payload(stars_payload(49, anonymous=True)) == (True, 49)
    assert parse_stars_payload(stars_payload(499, anonymous=False)) == (False, 499)


@pytest.mark.parametrize("payload", [None, "", "premium_stars:12", "premium_card:1", "donate"])
def test_foreign_payload_is_not_ours(payload):
    assert parse_stars_payload(payload) is None


@pytest.mark.parametrize("raw", ["donate_stars:0:1", "donate_stars:0:-5", "donate_stars:0:²",
                                 "donate_stars:0:abc", "donate_stars:1", "donate_stars"])
def test_bad_amount_falls_back_to_stars(raw):
    """Сумма вне границ или мусор — считаем по звёздам, а не верим строке."""
    parsed = parse_stars_payload(raw)
    assert parsed is not None
    assert parsed[1] is None


def test_payload_fits_telegram_limit():
    """Bot API: payload счёта — не длиннее 128 байт."""
    assert len(stars_payload(100_000, anonymous=True).encode()) <= 128


# --- разведение с Premium -----------------------------------------------------

def _message(**payment) -> Message:
    return Message.model_validate(
        {
            "message_id": 1,
            "date": 0,
            "chat": {"id": 777, "type": "private"},
            "from": TG_USER,
            **payment,
        }
    )


def _paid(payload: str, amount: int = 70, charge: str = "charge-1") -> Message:
    return _message(
        successful_payment={
            "currency": "XTR",
            "total_amount": amount,
            "invoice_payload": payload,
            "telegram_payment_charge_id": charge,
            "provider_payment_charge_id": "",
        }
    )


def _checkout(payload: str) -> PreCheckoutQuery:
    return PreCheckoutQuery.model_validate(
        {
            "id": "q1",
            "from": TG_USER,
            "currency": "XTR",
            "total_amount": 70,
            "invoice_payload": payload,
        }
    )


async def _accepting(observer, event) -> list[str]:
    """Имена обработчиков, чьи фильтры пропускают событие."""
    names = []
    # Фильтру Command нужен бот; в сеть он не ходит — у платёжного сообщения
    # нет текста, и проверка команды отказывает раньше.
    bot = Bot("42:TEST")
    try:
        for handler in observer.handlers:
            ok, _ = await handler.check(event, bot=bot)
            if ok:
                names.append(handler.callback.__name__)
    finally:
        await bot.session.close()
    return names


@pytest.mark.asyncio
async def test_donation_payment_never_reaches_premium():
    event = _paid(stars_payload(49, anonymous=False))
    assert await _accepting(premium.router.message, event) == []
    assert await _accepting(donate.router.message, event) == ["cb_donate_stars_paid"]


@pytest.mark.asyncio
async def test_premium_payment_never_reaches_donations():
    event = _paid("premium_stars:12")
    assert await _accepting(donate.router.message, event) == []
    assert await _accepting(premium.router.message, event) == ["cb_successful_payment"]


@pytest.mark.asyncio
async def test_pre_checkout_is_split_by_payload():
    donation = _checkout(stars_payload(49, anonymous=False))
    assert await _accepting(premium.router.pre_checkout_query, donation) == []
    assert await _accepting(donate.router.pre_checkout_query, donation) == [
        "cb_donate_pre_checkout"
    ]

    purchase = _checkout("premium_stars:1")
    assert await _accepting(donate.router.pre_checkout_query, purchase) == []
    assert await _accepting(premium.router.pre_checkout_query, purchase) == ["cb_pre_checkout"]


# --- полный проход апдейта через диспетчер -----------------------------------

@pytest.fixture(scope="module")
def dispatcher():
    """Порядок как в main.py: Premium раньше донатов. Роутеры — синглтоны
    модулей, и привязать их к диспетчеру можно только один раз.

    ⚠️ После модуля отвязываем: иначе тест старта, который зовёт настоящий
    main(), падает на «Router is already attached» — и падает только в полном
    прогоне, в одиночку проходит.
    """
    dp = Dispatcher()
    dp.include_routers(premium.router, donate.router)
    yield dp
    dp.sub_routers.clear()
    premium.router._parent_router = None
    donate.router._parent_router = None


@pytest.fixture
def wired(session, monkeypatch):
    """Хендлеры ходят в тестовую БД, наружу — никуда."""

    @asynccontextmanager
    async def factory():
        yield session

    monkeypatch.setattr(donate, "session_factory", factory)
    monkeypatch.setattr(premium, "session_factory", factory)

    async def forbidden(*_args, **_kwargs):
        raise AssertionError("донат выдал Premium")

    monkeypatch.setattr(premium, "activate_premium", forbidden)

    sent = {"thanks": [], "after": []}

    async def fake_notify(_session, _user, amount_rub, **kwargs):
        sent["thanks"].append((amount_rub, kwargs.get("via")))

    async def fake_after(_session, donation):
        sent["after"].append(donation.payment_id)

    monkeypatch.setattr("app.services.yookassa_payments.notify_donation", fake_notify)
    monkeypatch.setattr("app.services.goal_events.after_donation", fake_after)
    return sent


async def _feed(dp, **update):
    bot = Bot("42:TEST")
    try:
        await dp.feed_update(bot, Update.model_validate({"update_id": 1, **update}))
    finally:
        await bot.session.close()


async def _donations(session) -> list[Donation]:
    return list((await session.scalars(select(Donation))).all())


@pytest.mark.asyncio
async def test_stars_donation_recorded_and_no_premium(session, wired, dispatcher, stars_on):
    paid = _paid(stars_payload(49, anonymous=True), amount=70)
    await _feed(dispatcher, message=paid.model_dump(by_alias=True, exclude_none=True))

    [donation] = await _donations(session)
    assert donation.amount_rub == 49
    assert donation.stars == 70
    assert donation.provider == "stars"
    assert donation.is_anonymous is True
    assert donation.payment_id == "stars-charge-1"
    assert await session.scalar(select(func.count()).select_from(PremiumSubscription)) == 0
    assert wired["after"] == ["stars-charge-1"]
    assert wired["thanks"] == [(49, "звёздами, 70 ⭐")]


@pytest.mark.asyncio
async def test_stars_donation_is_idempotent(session, wired, dispatcher, stars_on):
    paid = _paid(stars_payload(49, anonymous=False), charge="same")
    body = paid.model_dump(by_alias=True, exclude_none=True)
    await _feed(dispatcher, message=body)
    await _feed(dispatcher, message=body)
    assert len(await _donations(session)) == 1
    assert len(wired["thanks"]) == 1


@pytest.mark.asyncio
async def test_amount_survives_rate_change(session, wired, dispatcher, monkeypatch):
    """Владелец обнулил курс между счётом и оплатой — в цель ложится сумма,
    которую человек видел на кнопке, а не ноль."""
    monkeypatch.setattr(settings, "stars_rub_rate", 0.0, raising=False)
    paid = _paid(stars_payload(149, anonymous=False), amount=213)
    await _feed(dispatcher, message=paid.model_dump(by_alias=True, exclude_none=True))
    [donation] = await _donations(session)
    assert donation.amount_rub == 149


@pytest.mark.asyncio
async def test_refund_removes_donation_from_rating(session, wired, dispatcher, stars_on, monkeypatch):
    async def no_refresh(_session):
        return True

    monkeypatch.setattr(donate.goal_post, "refresh_active", no_refresh)
    paid = _paid(stars_payload(49, anonymous=False), charge="to-refund")
    await _feed(dispatcher, message=paid.model_dump(by_alias=True, exclude_none=True))

    refund = _message(
        refunded_payment={
            "currency": "XTR",
            "total_amount": 70,
            "invoice_payload": stars_payload(49, anonymous=False),
            "telegram_payment_charge_id": "to-refund",
        }
    )
    await _feed(dispatcher, message=refund.model_dump(by_alias=True, exclude_none=True))
    [donation] = await _donations(session)
    assert donation.refunded_at is not None


@pytest.mark.asyncio
async def test_pre_checkout_answers_ok_for_donation(dispatcher, monkeypatch):
    answers = []

    async def fake_answer(_self, ok, error_message=None, **_kwargs):
        answers.append(ok)

    monkeypatch.setattr(PreCheckoutQuery, "answer", fake_answer)
    query = _checkout(stars_payload(49, anonymous=False))
    await _feed(dispatcher, pre_checkout_query=query.model_dump(by_alias=True, exclude_none=True))
    assert answers == [True]


# --- мидлвари не глотают оплату ----------------------------------------------

def test_payment_messages_are_recognised():
    assert is_payment_message(_paid("premium_stars:1"))
    assert not is_payment_message(_message(text="привет"))


def test_subscription_gate_lets_payment_through():
    """🔴 Отписался от канала между счётом и оплатой — раньше гейт гасил
    successful_payment, и списание оставалось без Premium и без доната."""
    assert _is_exempt(_paid(stars_payload(49, anonymous=False)))
    assert _is_exempt(_message(text="/paysupport"))


@pytest.mark.asyncio
async def test_throttling_never_drops_payment(monkeypatch):
    monkeypatch.setattr(settings, "admin_ids", "")
    middleware = ThrottlingMiddleware()
    calls = []

    async def handler(_event, _data):
        calls.append(1)

    class _U:
        id = 777

    # Человек под паузой антифлуда — а оплата всё равно доезжает.
    middleware._blocked_until[777] = float("inf")
    await middleware(handler, _paid("premium_stars:1"), {"event_from_user": _U()})
    assert calls == [1]


# --- экран выбора способа ------------------------------------------------------

def _targets(markup) -> list[str]:
    return [b.callback_data or b.url for row in markup.inline_keyboard for b in row]


def test_method_screen_with_all_three():
    targets = _targets(donate_method_keyboard(49, 0.2, "ru", show_ton=True, stars=70))
    assert targets == ["don:rub:49", "don:stars:49", "don:ton:49", "don:open"]


def test_method_screen_hides_disabled_ways():
    assert "don:stars:49" not in _targets(donate_method_keyboard(49, None, "ru", stars=None))
    assert "don:ton:49" not in _targets(donate_method_keyboard(49, None, "ru", show_ton=False, stars=70))


@pytest.mark.asyncio
async def test_paysupport_answers(session, monkeypatch):
    @asynccontextmanager
    async def factory():
        yield session

    monkeypatch.setattr(donate, "session_factory", factory)
    sent = []

    async def fake_answer(_self, text, **_kwargs):
        sent.append(text)

    monkeypatch.setattr(Message, "answer", fake_answer)
    await donate.cmd_paysupport(_message(text="/paysupport"))
    assert sent and settings.support_bot_username in sent[0]

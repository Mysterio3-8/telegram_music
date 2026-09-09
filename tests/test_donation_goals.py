"""Цели сбора: прогресс, одна активная, привязка донатов, текст поста.

Главное, что здесь стережётся, — деньги не должны переезжать между целями.
Донат приписан к той цели, что была активна в секунду оплаты, и заведение новой
цели не меняет прогресс старой ни в одну сторону.
"""
from datetime import datetime, timedelta

import pytest

from app.db.models import Donation, User
from app.services import donation_goals as goals
from app.services import goal_post
from app.services.donations import record_donation


async def _user(session, telegram_id: int, username: str | None = None) -> User:
    user = User(telegram_id=telegram_id, username=username)
    session.add(user)
    await session.flush()
    return user


async def _goal(session, title="Новый сервер", target=1000, **kwargs):
    goal = await goals.create_goal(session, title=title, target_rub=target, **kwargs)
    assert goal is not None
    return goal


# --- одна активная цель -----------------------------------------------------

async def test_second_active_goal_is_refused(session):
    await _goal(session)
    assert await goals.create_goal(session, title="Домен", target_rub=500) is None


async def test_new_goal_allowed_after_closing_previous(session):
    first = await _goal(session)
    await goals.close_goal(session, first)
    assert await goals.active_goal(session) is None
    second = await goals.create_goal(session, title="Домен", target_rub=500)
    assert second is not None
    assert (await goals.active_goal(session)).id == second.id


async def test_closed_goal_keeps_its_donations(session):
    """Закрытие — не удаление: история сбора должна остаться."""
    goal = await _goal(session)
    user = await _user(session, 1)
    await record_donation(session, user.id, 300, "pay-1")
    await goals.close_goal(session, goal)
    assert await goals.goal_progress(session, goal.id) == 300


# --- привязка донатов -------------------------------------------------------

async def test_donation_joins_active_goal(session):
    goal = await _goal(session)
    user = await _user(session, 1)
    donation = await record_donation(session, user.id, 250, "pay-1")
    assert donation.goal_id == goal.id
    assert await goals.goal_progress(session, goal.id) == 250


async def test_donation_without_goal_has_no_goal_id(session):
    user = await _user(session, 1)
    donation = await record_donation(session, user.id, 250, "pay-1")
    assert donation.goal_id is None


async def test_donations_before_goal_do_not_count(session):
    """Ответ владельца: в прогресс идут только новые донаты.

    Иначе полоса стартовала бы не с нуля деньгами, которые люди дали совсем на
    другое, — и это был бы обман, а не «выглядит живее».
    """
    user = await _user(session, 1)
    await record_donation(session, user.id, 900, "old-1")
    goal = await _goal(session)
    await record_donation(session, user.id, 100, "new-1")
    assert await goals.goal_progress(session, goal.id) == 100


async def test_new_goal_does_not_steal_previous_progress(session):
    first = await _goal(session, title="Сервер", target=1000)
    user = await _user(session, 1)
    await record_donation(session, user.id, 400, "pay-1")
    await goals.close_goal(session, first)

    second = await _goal(session, title="Домен", target=500)
    await record_donation(session, user.id, 100, "pay-2")

    assert await goals.goal_progress(session, first.id) == 400
    assert await goals.goal_progress(session, second.id) == 100


async def test_refunded_donation_leaves_progress(session):
    """Чарджбэк уводит деньги — полоса обязана уехать назад вслед за ними."""
    goal = await _goal(session)
    user = await _user(session, 1)
    donation = await record_donation(session, user.id, 500, "pay-1")
    assert await goals.goal_progress(session, goal.id) == 500
    donation.refunded_at = datetime.utcnow()
    await session.flush()
    assert await goals.goal_progress(session, goal.id) == 0


# --- достижение цели --------------------------------------------------------

async def test_mark_reached_fires_once(session):
    goal = await _goal(session, target=100)
    user = await _user(session, 1)
    await record_donation(session, user.id, 100, "pay-1")
    assert await goals.mark_reached(session, goal, 100) is True
    # Второй донат сверх цели не должен слать владельцу ещё одно поздравление.
    assert await goals.mark_reached(session, goal, 250) is False


async def test_mark_reached_ignores_underfunded_goal(session):
    goal = await _goal(session, target=1000)
    assert await goals.mark_reached(session, goal, 999) is False
    assert goal.reached_at is None


# --- рейтинг по цели --------------------------------------------------------

async def test_goal_top_sorts_by_sum(session):
    goal = await _goal(session)
    small = await _user(session, 1, "small")
    big = await _user(session, 2, "big")
    await record_donation(session, small.id, 100, "p1")
    await record_donation(session, big.id, 300, "p2")
    rows = await goals.goal_top(session, goal.id)
    assert [u.username for u, _ in rows] == ["big", "small"]


async def test_goal_top_hides_anonymous(session):
    """Аноним не должен всплывать в списке — но его деньги в прогрессе остаются."""
    goal = await _goal(session)
    shy = await _user(session, 1, "shy")
    loud = await _user(session, 2, "loud")
    await record_donation(session, shy.id, 900, "p1", is_anonymous=True)
    await record_donation(session, loud.id, 100, "p2")
    rows = await goals.goal_top(session, goal.id)
    assert [u.username for u, _ in rows] == ["loud"]
    assert await goals.goal_progress(session, goal.id) == 1000


async def test_goal_top_counts_only_its_own_goal(session):
    first = await _goal(session, title="Сервер")
    user = await _user(session, 1, "someone")
    await record_donation(session, user.id, 700, "p1")
    await goals.close_goal(session, first)
    second = await _goal(session, title="Домен")
    await record_donation(session, user.id, 30, "p2")
    rows = await goals.goal_top(session, second.id)
    assert rows == [(rows[0][0], 30)]


# --- полоса и проценты ------------------------------------------------------

@pytest.mark.parametrize(
    "raised,target,percent",
    [(0, 1000, 0), (500, 1000, 50), (1000, 1000, 100), (1400, 1000, 140)],
)
def test_progress_percent(raised, target, percent):
    assert goals.progress_percent(raised, target) == percent


def test_progress_percent_survives_zero_target():
    """Деление на ноль в отрисовке поста уронило бы обработку платежа."""
    assert goals.progress_percent(100, 0) == 0


def test_progress_bar_never_exceeds_width():
    """Сбор сверх цели закрашивает полосу целиком, но не удлиняет её —
    длинная полоса переносится на вторую строку и разваливает пост."""
    bar = goals.progress_bar(5000, 1000, width=10)
    assert len(bar) == 10
    assert bar == goals.BAR_FULL * 10


def test_progress_bar_shows_something_for_small_donation():
    """Пустая полоса рядом с «собрано 300 ₽» читается как «не собрано ничего»."""
    bar = goals.progress_bar(1, 1_000_000, width=12)
    assert bar.startswith(goals.BAR_FULL)


def test_progress_bar_empty_at_zero():
    assert goals.progress_bar(0, 1000, width=8) == goals.BAR_EMPTY * 8


# --- срок -------------------------------------------------------------------

async def test_days_left_counts_down(session):
    goal = await _goal(session, deadline=datetime.utcnow() + timedelta(days=3))
    assert goals.days_left(goal) == 3


async def test_days_left_negative_after_deadline(session):
    goal = await _goal(session, deadline=datetime.utcnow() - timedelta(days=2))
    assert goals.days_left(goal) < 0


async def test_days_left_none_without_deadline(session):
    goal = await _goal(session)
    assert goals.days_left(goal) is None


# --- текст поста ------------------------------------------------------------

async def test_post_contains_progress_and_amounts(session):
    goal = await _goal(session, title="Новый сервер", target=1000)
    text = goal_post.render_post(goal, 250, [])
    assert "Новый сервер" in text
    assert "25%" in text
    assert "1 000" in text


async def test_post_escapes_title(session):
    """Название пишет человек. Незакрытый тег — это не «некрасиво», это отказ
    Telegram публиковать пост целиком."""
    goal = await _goal(session, title="Сервер & <хостинг>")
    text = goal_post.render_post(goal, 0, [])
    assert "&amp;" in text and "&lt;хостинг&gt;" in text
    assert "<хостинг>" not in text


async def test_post_hides_anonymous_names(session):
    goal = await _goal(session)
    user = await _user(session, 1, "loud")
    text = goal_post.render_post(goal, 100, [(user, 100, True)])
    assert "Аноним" in text
    assert "loud" not in text


async def test_post_shows_reached_line(session):
    goal = await _goal(session, target=100)
    goal.reached_at = datetime.utcnow()
    text = goal_post.render_post(goal, 100, [])
    assert "собрана" in text.lower()


async def test_post_fits_photo_caption_limit(session):
    """У фото-поста подпись ограничена 1024 символами. Обрезаем по строкам:
    обрубок по символам рвёт HTML-тег пополам, и пост не публикуется вовсе."""
    goal = await _goal(session, title="Сервер", description="о" * 3000)
    text = goal_post.render_post(goal, 10, [])
    fitted = goal_post._fit(text, goal_post.CAPTION_LIMIT)
    assert len(fitted) <= goal_post.CAPTION_LIMIT
    assert fitted.count("<b>") == fitted.count("</b>")

from datetime import timedelta

from app.config import settings
from app.db.models import TrackEvent, User
from app.services.gamification import (
    _scaled_reward,
    build_achievements,
    count_referrals,
    register_referral,
    UserStats,
)
from app.services.premium import _utcnow
from app.services.revenue import collect_revenue, record_payment


def test_scaled_reward_cuts_giveaway(monkeypatch):
    monkeypatch.setattr(settings, "premium_reward_factor", 0.25)
    assert _scaled_reward(120) == 30
    assert _scaled_reward(3) == 0  # мелкие награды обнуляются
    from app.services.gamification import LIFETIME_DAYS

    assert _scaled_reward(LIFETIME_DAYS) == LIFETIME_DAYS  # «навсегда» не режем


def test_achievements_use_scaled_rewards(monkeypatch):
    monkeypatch.setattr(settings, "premium_reward_factor", 0.0)
    stats = UserStats(
        listens=100000, listen_hours=0, streak_days=0, favorites=0, playlists=0,
        invited=0, has_premium_ever=False, premium_year=False, premium_forever=False,
        uploads=0, artists=0, downloads=0,
    )
    # при факторе 0 ни одно достижение не даёт дней (кроме «навсегда», которых тут нет)
    assert all(a.reward_days == 0 for a in build_achievements(stats))


async def _user(session, tid, referred_by=None) -> User:
    u = User(telegram_id=tid, referred_by=referred_by)
    session.add(u)
    await session.commit()
    return u


async def test_count_referrals_only_active(session):
    referrer = await _user(session, 100)
    active = await _user(session, 101, referred_by=100)
    await _user(session, 102, referred_by=100)  # без прослушиваний — не в счёт
    session.add(TrackEvent(user_id=active.id, track_id=1, event="listen"))
    await session.commit()
    # засчитан только «живой» приглашённый (антинакрутка)
    assert await count_referrals(session, 100) == 1


async def test_register_referral_write_once(session):
    await _user(session, 200)
    invited = await _user(session, 201)
    assert await register_referral(session, invited, 200) is True
    # повторная привязка к другому рефереру не проходит
    assert await register_referral(session, invited, 999) is False


async def test_revenue_stats(session):
    user = await _user(session, 300)
    await record_payment(session, user.id, 49, "yookassa", "p1")
    await record_payment(session, user.id, 49, "card", "p2")
    await record_payment(session, user.id, 0, "stars", "p3")  # не в рублёвую выручку
    rev = await collect_revenue(session)
    assert rev.total == 98
    assert rev.payments_total == 2
    assert rev.day == 98

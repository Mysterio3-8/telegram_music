from datetime import timedelta

from app.db.models import Contest, TrackEvent, User
from app.services.contests import (
    active_contests,
    award_winner,
    check_eligibility,
    eligible_participants,
    join_contest,
    participant_count,
    pick_winner,
)
from app.services.premium import _utcnow, is_premium_active


async def _add_user(session, telegram_id: int) -> User:
    user = User(telegram_id=telegram_id)
    session.add(user)
    await session.commit()
    return user


async def _add_contest(session, **kwargs) -> Contest:
    kwargs.setdefault("title", "Розыгрыш Premium")
    kwargs.setdefault("description", "Условия конкурса")
    kwargs.setdefault("banner_text", "Выиграй Premium")
    kwargs.setdefault("prize_days", 30)
    kwargs.setdefault("ends_at", _utcnow() + timedelta(days=15))
    contest = Contest(**kwargs)
    session.add(contest)
    await session.commit()
    return contest


async def test_active_contests_skips_finished_and_drawn(session):
    live = await _add_contest(session)
    await _add_contest(session, ends_at=_utcnow() - timedelta(days=1))
    await _add_contest(session, drawn_at=_utcnow(), is_active=False)

    assert [c.id for c in await active_contests(session)] == [live.id]


async def test_join_requires_conditions_and_is_idempotent(session):
    contest = await _add_contest(session, required_channel="@tgramuzuka", required_referrals=1)
    user = await _add_user(session, 100)
    invited = User(telegram_id=200, referred_by=100)
    session.add(invited)
    await session.commit()
    # «живой» приглашённый (антинакрутка засчитывает только с прослушиванием)
    session.add(TrackEvent(user_id=invited.id, track_id=1, event="listen"))
    await session.commit()

    not_subscribed = await check_eligibility(session, contest, user, channel_subscribed=False)
    assert not_subscribed.can_join is False
    assert await join_contest(session, contest, user, not_subscribed) is False

    eligible = await check_eligibility(session, contest, user, channel_subscribed=True)
    assert eligible.referrals == 1
    assert await join_contest(session, contest, user, eligible) is True

    # Повторное нажатие «Участвовать» не создаёт второго участия
    again = await check_eligibility(session, contest, user, channel_subscribed=True)
    assert again.joined is True
    assert await join_contest(session, contest, user, again) is False
    assert await participant_count(session, contest.id) == 1


async def test_join_without_required_channel_needs_no_subscription(session):
    contest = await _add_contest(session)
    user = await _add_user(session, 100)

    eligibility = await check_eligibility(session, contest, user, channel_subscribed=False)
    assert eligibility.can_join is True
    assert await join_contest(session, contest, user, eligibility) is True


async def test_draw_excludes_participant_who_lost_referrals(session):
    contest = await _add_contest(session, required_referrals=1)
    honest = await _add_user(session, 100)
    cheater = await _add_user(session, 300)
    invited = User(telegram_id=200, referred_by=100)
    unbound = User(telegram_id=400, referred_by=300)
    session.add_all([invited, unbound])
    await session.commit()
    # оба приглашённых «живые» на момент вступления
    session.add_all([
        TrackEvent(user_id=invited.id, track_id=1, event="listen"),
        TrackEvent(user_id=unbound.id, track_id=1, event="listen"),
    ])
    await session.commit()

    for user in (honest, cheater):
        eligibility = await check_eligibility(session, contest, user, channel_subscribed=True)
        assert await join_contest(session, contest, user, eligibility) is True

    # Приглашённый «отвязался» — условие больше не выполнено
    unbound.referred_by = None
    await session.commit()

    candidates = await eligible_participants(session, contest)
    assert [u.id for u in candidates] == [honest.id]


async def test_award_winner_grants_premium_and_closes_contest(session):
    contest = await _add_contest(session, prize_days=30)
    winner = await _add_user(session, 100)

    await award_winner(session, contest, winner)

    assert is_premium_active(winner) is True
    assert winner.premium_until > _utcnow() + timedelta(days=29)
    assert contest.winner_user_id == winner.id
    assert contest.is_active is False
    assert contest.drawn_at is not None


async def test_award_forever_prize(session):
    contest = await _add_contest(session, prize_days=0)
    winner = await _add_user(session, 100)

    await award_winner(session, contest, winner)

    assert winner.premium_until > _utcnow() + timedelta(days=365 * 50)


def test_pick_winner_on_empty_list_returns_none():
    assert pick_winner([]) is None

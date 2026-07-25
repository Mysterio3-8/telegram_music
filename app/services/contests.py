"""Конкурсы с розыгрышем Premium: условия участия, участие, выбор победителя.

Все условия проверяются на сервере — клиент не может «пройти» их сам (SPEC-2.0,
инвариант «никаких накруток»). Подписка на канал проверяется вызывающей стороной
(там есть Bot) и приходит сюда готовым флагом — сервис не знает о Telegram.
"""
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Contest, ContestParticipant, User
from app.services.gamification import count_referrals

# Premium «навсегда» победителю — та же механика, что в тарифе «навсегда»
FOREVER_DAYS = 365 * 100


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@dataclass(frozen=True)
class Eligibility:
    """Состояние условий участия конкретного пользователя."""

    is_subscribed: bool
    referrals: int
    required_referrals: int
    joined: bool

    @property
    def can_join(self) -> bool:
        return self.is_subscribed and self.referrals >= self.required_referrals


async def active_contests(session: AsyncSession) -> list[Contest]:
    """Идущие конкурсы: активные, ещё не разыгранные, срок не истёк."""
    rows = await session.scalars(
        select(Contest)
        .where(Contest.is_active.is_(True), Contest.drawn_at.is_(None), Contest.ends_at > _utcnow())
        .order_by(Contest.ends_at)
    )
    return list(rows)


async def get_contest(session: AsyncSession, contest_id: int) -> Contest | None:
    return await session.get(Contest, contest_id)


async def is_participant(session: AsyncSession, contest_id: int, user_id: int) -> bool:
    found = await session.scalar(
        select(ContestParticipant.id).where(
            ContestParticipant.contest_id == contest_id, ContestParticipant.user_id == user_id
        )
    )
    return found is not None


async def participant_count(session: AsyncSession, contest_id: int) -> int:
    total = await session.scalar(
        select(func.count()).select_from(ContestParticipant).where(
            ContestParticipant.contest_id == contest_id
        )
    )
    return total or 0


async def check_eligibility(
    session: AsyncSession, contest: Contest, user: User, *, channel_subscribed: bool
) -> Eligibility:
    """Считает выполнение условий. Канал не задан — подписка не требуется."""
    referrals = await count_referrals(session, user.telegram_id)
    return Eligibility(
        is_subscribed=channel_subscribed if contest.required_channel else True,
        referrals=referrals,
        required_referrals=contest.required_referrals,
        joined=await is_participant(session, contest.id, user.id),
    )


async def join_contest(
    session: AsyncSession, contest: Contest, user: User, eligibility: Eligibility
) -> bool:
    """Регистрирует участие. False — условия не выполнены или уже участвует."""
    if eligibility.joined or not eligibility.can_join:
        return False
    session.add(
        ContestParticipant(
            contest_id=contest.id, user_id=user.id, referrals_at_join=eligibility.referrals
        )
    )
    await session.commit()
    return True


async def eligible_participants(session: AsyncSession, contest: Contest) -> list[User]:
    """Участники, у которых условия выполнены и на момент розыгрыша.

    Приглашённых пересчитываем заново: накрученные на момент участия рефералы,
    которых потом стало меньше, не должны попасть в барабан.
    """
    rows = await session.scalars(
        select(User)
        .join(ContestParticipant, ContestParticipant.user_id == User.id)
        .where(ContestParticipant.contest_id == contest.id)
    )
    winners: list[User] = []
    for user in rows:
        if await count_referrals(session, user.telegram_id) >= contest.required_referrals:
            winners.append(user)
    return winners


def pick_winner(candidates: list[User]) -> User | None:
    """Случайный выбор криптостойким генератором — жеребьёвку нельзя предсказать."""
    return secrets.choice(candidates) if candidates else None


async def award_winner(session: AsyncSession, contest: Contest, winner: User) -> None:
    """Выдаёт приз победителю и закрывает конкурс."""
    now = _utcnow()
    base = winner.premium_until if (winner.premium_until and winner.premium_until > now) else now
    days = FOREVER_DAYS if contest.prize_days == 0 else contest.prize_days
    winner.premium = True
    winner.premium_until = base + timedelta(days=days)
    contest.winner_user_id = winner.id
    contest.drawn_at = now
    contest.is_active = False
    await session.commit()

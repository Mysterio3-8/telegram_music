"""Конкурсы в Mini App: список активных и участие (SPEC-2.0 §28).

Условия проверяются здесь, на сервере: клиент присылает только намерение
участвовать. Подписка на канал — тем же getChatMember с TTL-кэшем, что и в гейте.
"""
from aiogram import Bot
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.api.schemas import ContestJoinOut, ContestOut
from app.config import settings
from app.db.models import Contest, User
from app.services.contests import (
    Eligibility,
    active_contests,
    check_eligibility,
    contest_channel_url,
    get_contest,
    join_contest,
    participant_count,
)
from app.services.subscription import is_channel_subscribed

router = APIRouter(tags=["contests"])


async def _eligibility(
    session: AsyncSession, contest: Contest, user: User, bot: Bot | None, force: bool = False
) -> Eligibility:
    subscribed = True
    if contest.required_channel and bot is not None:
        subscribed = await is_channel_subscribed(
            session, bot, user.id, user.telegram_id, contest.required_channel, force
        )
    return await check_eligibility(session, contest, user, channel_subscribed=subscribed)


async def _to_out(session: AsyncSession, contest: Contest, eligibility: Eligibility) -> ContestOut:
    return ContestOut(
        id=contest.id,
        title=contest.title,
        description=contest.description,
        banner_text=contest.banner_text,
        prize_days=contest.prize_days,
        ends_at=contest.ends_at,
        participants=await participant_count(session, contest.id),
        joined=eligibility.joined,
        can_join=eligibility.can_join and not eligibility.joined,
        is_subscribed=eligibility.is_subscribed,
        referrals=eligibility.referrals,
        required_referrals=eligibility.required_referrals,
        channel_url=contest_channel_url(contest),
    )


@router.get("/contests", response_model=list[ContestOut])
async def list_contests(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[ContestOut]:
    contests = await active_contests(session)
    if not contests:
        return []

    needs_bot = any(contest.required_channel for contest in contests)
    bot = Bot(token=settings.bot_token) if needs_bot else None
    try:
        return [
            await _to_out(session, contest, await _eligibility(session, contest, user, bot))
            for contest in contests
        ]
    finally:
        if bot is not None:
            await bot.session.close()


@router.post("/contests/{contest_id}/join", response_model=ContestJoinOut)
async def join(
    contest_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ContestJoinOut:
    contest = await get_contest(session, contest_id)
    if contest is None or not contest.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Конкурс не найден")

    bot = Bot(token=settings.bot_token) if contest.required_channel else None
    try:
        # force=True: пользователь только что подписался — кэш обязан обновиться
        eligibility = await _eligibility(session, contest, user, bot, force=True)
    finally:
        if bot is not None:
            await bot.session.close()

    joined = await join_contest(session, contest, user, eligibility)
    if not joined and not eligibility.joined:
        raise HTTPException(status.HTTP_409_CONFLICT, "Условия конкурса ещё не выполнены")

    fresh = await check_eligibility(
        session, contest, user, channel_subscribed=eligibility.is_subscribed
    )
    return ContestJoinOut(joined=True, contest=await _to_out(session, contest, fresh))

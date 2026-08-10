"""Реферальная программа в боте — то же, что на экране Mini App, но текстом.

Источник правды один: пороги и ранги берутся из services/gamification, а не
дублируются здесь. Экран Mini App свои пороги зеркалит константой — тут этой
ошибки не повторяем.
"""
from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.i18n import plural, t
from app.config import settings
from app.db.base import session_factory
from app.db.models import User
from app.handlers.common import ensure_user
from app.keyboards.referral import referral_keyboard
from app.services.gamification import (
    LIFETIME_DAYS,
    REFERRAL_MILESTONES,
    count_referrals,
    grant_referral_milestones,
    next_referral_reward,
    referral_link,
    referral_rank,
)

router = Router()


def _friends_word(count: int) -> str:
    return plural("word.friends", count)


def _reward_text(days: int) -> str:
    """Награда словами. Пороги заданы владельцем дословно и не урезаются
    множителем, поэтому показываем ровно то, что начислим."""
    if days >= LIFETIME_DAYS:
        return t("referral.forever")
    return t("referral.reward_days", days=days, days_word=plural("word.days", days))


def _rewards_block(invited: int) -> str:
    """Вся лестница порогов: достигнутые с галочкой, остальные с подарком.
    Список показывается целиком (решение владельца) — верхние пороги и есть
    главная мотивация звать дальше, обрезать их незачем."""

    def line(threshold: int, days: int) -> str:
        mark = "✅" if threshold <= invited else "🎁"
        return f"{mark} {threshold} {_friends_word(threshold)} — {_reward_text(days)}"

    return "\n".join(line(threshold, days) for threshold, days in REFERRAL_MILESTONES)


async def build_referral_text(session: AsyncSession, user: User) -> str:
    # Открытие экрана — момент начисления заработанного, как и в Mini App
    await grant_referral_milestones(session, user)
    invited = await count_referrals(session, user.telegram_id)
    progress = referral_rank(invited)
    to_next_reward, next_reward_days = next_referral_reward(invited)
    link = referral_link(user.telegram_id, settings.bot_username)

    rank_line = ""
    if progress.current:
        rank_line = (
            t("referral.rank", emoji=progress.current.emoji, title=progress.current.title) + "\n"
        )
    if progress.next:
        rank_line += (
            t(
                "referral.to_next_rank",
                emoji=progress.next.emoji,
                title=progress.next.title,
                count=progress.to_next,
                friends_word=_friends_word(progress.to_next),
            )
            + "\n"
        )

    next_line = ""
    if to_next_reward and next_reward_days:
        next_line = t(
            "referral.next_reward",
            count=to_next_reward,
            friends_word=_friends_word(to_next_reward),
            reward=_reward_text(next_reward_days),
        )

    return (
        t("referral.title") + "\n\n"
        + t("referral.invited", count=invited) + "\n"
        + rank_line
        + next_line + "\n"
        + t("referral.your_link") + "\n"
        + f"<code>{link}</code>\n\n"
        + t("referral.rewards") + "\n"
        + _rewards_block(invited)
    )


async def _show(callback: CallbackQuery) -> None:
    async with session_factory() as session:
        user = await ensure_user(session, callback.from_user)
        text = await build_referral_text(session, user)
        link = referral_link(user.telegram_id, settings.bot_username)
    # parse_mode обязателен: глобального дефолта у бота нет, без него теги
    # приезжают пользователю текстом («</b>» прямо в сообщении)
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=referral_keyboard(link),
        disable_web_page_preview=True,
    )


@router.callback_query(F.data == "menu:referral")
async def open_referral(callback: CallbackQuery) -> None:
    await _show(callback)
    await callback.answer()


@router.callback_query(F.data == "ref:refresh")
async def refresh_referral(callback: CallbackQuery) -> None:
    try:
        await _show(callback)
    except Exception:  # noqa: BLE001 — Telegram отвергает edit с тем же текстом
        await callback.answer(t("common.no_changes"))
        return
    await callback.answer(t("common.updated"))

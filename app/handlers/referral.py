"""Реферальная программа в боте — то же, что на экране Mini App, но текстом.

Источник правды один: пороги и ранги берутся из services/gamification, а не
дублируются здесь. Экран Mini App свои пороги зеркалит константой — тут этой
ошибки не повторяем.
"""
from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.base import session_factory
from app.db.models import User
from app.handlers.common import ensure_user
from app.keyboards.referral import referral_keyboard
from app.services.gamification import (
    REFERRAL_MILESTONES,
    count_referrals,
    grant_referral_milestones,
    next_referral_reward,
    referral_link,
    referral_rank,
)

router = Router()

_VISIBLE_MILESTONES = 5  # весь список из 13 порогов в сообщении не нужен — только ближайшие


def _friends_word(count: int) -> str:
    if count % 10 == 1 and count % 100 != 11:
        return "друг"
    if count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14):
        return "друга"
    return "друзей"


def _days_word(days: int) -> str:
    if days % 10 == 1 and days % 100 != 11:
        return "день"
    if days % 10 in (2, 3, 4) and days % 100 not in (12, 13, 14):
        return "дня"
    return "дней"


def _rewards_block(invited: int) -> str:
    """Ближайшие пороги: достигнутые с галочкой, остальные с подарком."""
    upcoming = [row for row in REFERRAL_MILESTONES if row[0] > invited][:_VISIBLE_MILESTONES]
    reached = [row for row in REFERRAL_MILESTONES if row[0] <= invited][-2:]
    lines = [
        f"✅ {threshold} {_friends_word(threshold)} — {days} {_days_word(days)}"
        for threshold, days in reached
    ]
    lines += [
        f"🎁 {threshold} {_friends_word(threshold)} — {days} {_days_word(days)}"
        for threshold, days in upcoming
    ]
    return "\n".join(lines)


async def build_referral_text(session: AsyncSession, user: User) -> str:
    # Открытие экрана — момент начисления заработанного, как и в Mini App
    await grant_referral_milestones(session, user)
    invited = await count_referrals(session, user.telegram_id)
    progress = referral_rank(invited)
    to_next_reward, next_reward_days = next_referral_reward(invited)
    link = referral_link(user.telegram_id, settings.bot_username)

    rank_line = ""
    if progress.current:
        rank_line = f"{progress.current.emoji} Ранг: <b>{progress.current.title}</b>\n"
    if progress.next:
        rank_line += (
            f"До ранга {progress.next.emoji} {progress.next.title} — "
            f"ещё {progress.to_next} {_friends_word(progress.to_next)}\n"
        )

    next_line = ""
    if to_next_reward and next_reward_days:
        next_line = (
            f"\n🔥 Ещё {to_next_reward} {_friends_word(to_next_reward)} — "
            f"и {next_reward_days} {_days_word(next_reward_days)} Premium\n"
        )

    return (
        "🎁 <b>Реферальная программа</b>\n\n"
        "<b>Один друг — неделя Premium.</b> Награда приходит автоматически, "
        "как только друг откроет бота по вашей ссылке.\n\n"
        f"👥 Приглашено: <b>{invited}</b>\n"
        f"{rank_line}"
        f"{next_line}\n"
        "<b>Ваша ссылка</b> (нажмите, чтобы скопировать):\n"
        f"<code>{link}</code>\n\n"
        "<b>Награды</b>\n"
        f"{_rewards_block(invited)}\n\n"
        "Когда друг оплачивает подписку, вам падает скидка 50% на следующую покупку."
    )


async def _show(callback: CallbackQuery) -> None:
    async with session_factory() as session:
        user = await ensure_user(session, callback.from_user)
        text = await build_referral_text(session, user)
        link = referral_link(user.telegram_id, settings.bot_username)
    await callback.message.edit_text(
        text, reply_markup=referral_keyboard(link), disable_web_page_preview=True
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
        await callback.answer("Пока без изменений")
        return
    await callback.answer("Обновлено")

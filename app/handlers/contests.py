"""Участие в конкурсе из бота: кнопка «Участвовать» под постом (SPEC-2.0 §28).

Условия проверяются на сервере при каждом нажатии — кнопка сама по себе ничего
не подтверждает. Подписку перепроверяем принудительно: пользователь обычно
подписывается прямо перед нажатием, кэш обязан обновиться.
"""
from aiogram import F, Router
from aiogram.types import CallbackQuery

from app.db.base import session_factory
from app.handlers.common import ensure_user
from app.keyboards.contests import contest_keyboard
from app.services.contests import check_eligibility, get_contest, join_contest
from app.services.subscription import is_channel_subscribed

router = Router()

ALREADY_JOINED = "Вы уже участвуете — ждём итогов 🍀"
JOINED = "🎉 Вы в списке участников! Удачи в розыгрыше"
CONTEST_CLOSED = "Конкурс завершён"


def _requirements_text(referrals: int, required: int, subscribed: bool) -> str:
    lines = ["Условия ещё не выполнены:"]
    if not subscribed:
        lines.append("• подпишитесь на канал")
    if referrals < required:
        lines.append(f"• пригласите друзей: {referrals} из {required}")
    return "\n".join(lines)


@router.callback_query(F.data.startswith("contest:join:"))
async def cb_contest_join(callback: CallbackQuery) -> None:
    contest_id = int(callback.data.removeprefix("contest:join:"))

    async with session_factory() as session:
        user = await ensure_user(session, callback.from_user)
        contest = await get_contest(session, contest_id)
        if contest is None or not contest.is_active:
            await callback.answer(CONTEST_CLOSED, show_alert=True)
            return

        subscribed = True
        if contest.required_channel:
            subscribed = await is_channel_subscribed(
                session, callback.bot, user.id, user.telegram_id, contest.required_channel, True
            )

        eligibility = await check_eligibility(
            session, contest, user, channel_subscribed=subscribed
        )
        if eligibility.joined:
            await callback.answer(ALREADY_JOINED, show_alert=True)
            return

        if not await join_contest(session, contest, user, eligibility):
            await callback.answer(
                _requirements_text(
                    eligibility.referrals, eligibility.required_referrals, eligibility.is_subscribed
                ),
                show_alert=True,
            )
            return

        markup = contest_keyboard(contest, joined=True)

    await callback.answer(JOINED, show_alert=True)
    if callback.message is not None:
        await callback.message.edit_reply_markup(reply_markup=markup)

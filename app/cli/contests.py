"""Конкурсы: создание, список, розыгрыш.

  python -m app.cli.contests create --title "Розыгрыш Premium" --ends 2026-08-09 \
      --prize-days 30 --channel @tgramuzuka --referrals 1
  python -m app.cli.contests list
  python -m app.cli.contests announce <id> [--preview]
  python -m app.cli.contests draw <id> [--dry]

Розыгрыш перепроверяет условия на момент запуска: подписку — живым запросом
к Telegram, приглашённых — заново по базе. Накрутившие и отписавшиеся в барабан
не попадают.
"""
import argparse
import asyncio
import logging
from datetime import datetime

from aiogram import Bot

from app.config import settings
from app.db.base import session_factory
from app.db.models import User
from app.services.contests import (
    active_contests,
    award_winner,
    eligible_participants,
    get_contest,
    participant_count,
    pick_winner,
)
from app.services.subscription import check_channel_membership

logger = logging.getLogger("contests-cli")

WINNER_MESSAGE = (
    "🎉 Поздравляем! Вы победили в конкурсе «{title}».\n\n"
    "Premium уже активирован — ничего делать не нужно. Приятного прослушивания!"
)

# Пост рассылки. Кнопка «Участвовать» приходит вместе с сообщением, поэтому
# отдельным пунктом условий её не пишем — на неё жмут в конце.
ANNOUNCE_TEMPLATE = """🎉 Розыгрыш TG Music Premium!

Разыгрываем подписку TG Music Premium — участвовать можно прямо здесь.

Что нужно сделать:
✅ Подписаться на наш канал{channel}
✅ Пригласить друзей в TG Music
✅ Сделать репост записи во ВКонтакте или в Telegram Stories
✅ Нажать кнопку «Участвовать» ниже

🏆 Итоги — {ends}.
🎲 Победителя выбираем случайным образом среди тех, кто выполнил условия.
⚡ Premium победителю активируется автоматически — делать ничего не нужно.

🍀 Удачи!"""


def _announce_text(contest) -> str:
    """Текст поста: описание конкурса, если владелец задал своё, иначе шаблон."""
    if contest.description.strip():
        return contest.description
    channel = f": {contest.required_channel}" if contest.required_channel else ""
    return ANNOUNCE_TEMPLATE.format(channel=channel, ends=f"{contest.ends_at:%d %B}")


async def _create(args: argparse.Namespace) -> None:
    from app.db.models import Contest

    async with session_factory() as session:
        contest = Contest(
            title=args.title,
            description=args.description,
            banner_text=args.banner or args.title,
            prize_days=args.prize_days,
            required_channel=args.channel,
            required_referrals=args.referrals,
            ends_at=datetime.fromisoformat(args.ends),
        )
        session.add(contest)
        await session.commit()
        print(f"Конкурс создан: id={contest.id} «{contest.title}» до {contest.ends_at:%d.%m.%Y}")


async def _list() -> None:
    async with session_factory() as session:
        contests = await active_contests(session)
        if not contests:
            print("Активных конкурсов нет")
            return
        for contest in contests:
            total = await participant_count(session, contest.id)
            prize = "навсегда" if contest.prize_days == 0 else f"{contest.prize_days} дн."
            print(
                f"id={contest.id} «{contest.title}» до {contest.ends_at:%d.%m.%Y} "
                f"приз={prize} участников={total} канал={contest.required_channel or '—'} "
                f"друзей={contest.required_referrals}"
            )


async def _announce(contest_id: int, preview: bool) -> None:
    from app.tasks.broadcast import send_broadcast

    async with session_factory() as session:
        contest = await get_contest(session, contest_id)
        if contest is None:
            print(f"Конкурс {contest_id} не найден")
            return
        text = _announce_text(contest)

    if preview:
        print("--- предпросмотр поста ---")
        print(text)
        print("--- кнопки: подписка на канал, «Участвовать», открыть TG Music ---")
        return

    admin_chat_id = min(settings.admin_id_set, default=0)
    if not admin_chat_id:
        print("Не задан ADMIN_IDS — некуда прислать отчёт о рассылке")
        return
    send_broadcast.delay(text, None, admin_chat_id, contest.id)
    print(f"Рассылка поставлена в очередь. Отчёт придёт админу {admin_chat_id}")


async def _subscribed_only(bot: Bot, channel: str, candidates: list[User]) -> list[User]:
    """Оставляет тех, кто подписан на канал прямо сейчас."""
    confirmed: list[User] = []
    for user in candidates:
        if await check_channel_membership(bot, user.telegram_id, channel):
            confirmed.append(user)
    return confirmed


async def _draw(contest_id: int, dry: bool) -> None:
    async with session_factory() as session:
        contest = await get_contest(session, contest_id)
        if contest is None:
            print(f"Конкурс {contest_id} не найден")
            return
        if contest.drawn_at is not None:
            print(f"Конкурс уже разыгран {contest.drawn_at:%d.%m.%Y}, победитель id={contest.winner_user_id}")
            return

        total = await participant_count(session, contest.id)
        candidates = await eligible_participants(session, contest)

        bot = Bot(token=settings.bot_token)
        try:
            if contest.required_channel:
                candidates = await _subscribed_only(bot, contest.required_channel, candidates)

            print(f"Участников: {total}, прошли перепроверку условий: {len(candidates)}")
            winner = pick_winner(candidates)
            if winner is None:
                print("Некому вручать приз — условия не выполнил никто")
                return
            if dry:
                print(f"[dry] Победил бы: telegram_id={winner.telegram_id} (id={winner.id})")
                return

            await award_winner(session, contest, winner)
            print(f"Победитель: telegram_id={winner.telegram_id}, Premium до {winner.premium_until:%d.%m.%Y}")
            try:
                await bot.send_message(
                    winner.telegram_id, WINNER_MESSAGE.format(title=contest.title)
                )
            except Exception:  # noqa: BLE001 — приз уже начислен, доставка не критична
                logger.warning("Победителю %s не удалось отправить сообщение", winner.telegram_id)
        finally:
            await bot.session.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Конкурсы: создание и розыгрыш")
    sub = parser.add_subparsers(dest="command", required=True)

    p_create = sub.add_parser("create", help="Создать конкурс")
    p_create.add_argument("--title", required=True)
    p_create.add_argument("--ends", required=True, help="Дата итогов, ГГГГ-ММ-ДД")
    p_create.add_argument("--description", default="", help="Полный текст условий")
    p_create.add_argument("--banner", default=None, help="Короткий текст баннера")
    p_create.add_argument("--prize-days", type=int, default=30, help="0 — Premium навсегда")
    p_create.add_argument("--channel", default=None, help="Канал-условие, @username")
    p_create.add_argument("--referrals", type=int, default=0, help="Сколько друзей пригласить")

    sub.add_parser("list", help="Активные конкурсы")

    p_announce = sub.add_parser("announce", help="Разослать пост о конкурсе всем пользователям")
    p_announce.add_argument("contest_id", type=int)
    p_announce.add_argument("--preview", action="store_true", help="Показать текст, не рассылая")

    p_draw = sub.add_parser("draw", help="Разыграть приз")
    p_draw.add_argument("contest_id", type=int)
    p_draw.add_argument("--dry", action="store_true", help="Показать победителя, не выдавая приз")

    args = parser.parse_args()

    if args.command == "create":
        asyncio.run(_create(args))
    elif args.command == "list":
        asyncio.run(_list())
    elif args.command == "announce":
        asyncio.run(_announce(args.contest_id, args.preview))
    elif args.command == "draw":
        asyncio.run(_draw(args.contest_id, args.dry))


if __name__ == "__main__":
    main()

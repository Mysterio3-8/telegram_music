"""Цели сбора из командной строки.

    python -m app.cli.goals list
    python -m app.cli.goals create "Новый сервер" 30000 --description "..." --days 30
    python -m app.cli.goals publish [--chat -1001234567890]
    python -m app.cli.goals refresh
    python -m app.cli.goals close

Дублирует админку в боте намеренно. Админка — чтобы владелец делал всё с
телефона; CLI — чтобы можно было починить руками, когда бот не отвечает, и
чтобы проверить публикацию, не отправляя ничего людям (`--dry`).
"""
import argparse
import asyncio
import sys
from datetime import datetime, timedelta, timezone

from app.config import settings
from app.db.base import session_factory
from app.services import donation_goals as goals
from app.services import goal_post


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def cmd_list() -> int:
    async with session_factory() as session:
        goal = await goals.active_goal(session)
        if goal is None:
            print("Активной цели нет.")
            return 0
        raised = await goals.goal_progress(session, goal.id)
        percent = goals.progress_percent(raised, goal.target_rub)
        print(f"Цель #{goal.id}: {goal.title}")
        print(f"  собрано: {raised} из {goal.target_rub} ₽ ({percent}%)")
        print(f"  полоса:  {goals.progress_bar(raised, goal.target_rub)}")
        left = goals.days_left(goal)
        if left is not None:
            print(f"  срок:    осталось дней {left}")
        if goal.reached_at:
            print(f"  достигнута: {goal.reached_at}")
        if goal.channel_message_id:
            print(f"  пост:    chat={goal.channel_chat_id} msg={goal.channel_message_id}")
        else:
            print("  пост:    не опубликован")
        recent = await goals.recent_donations(session, goal.id)
        if recent:
            print("  последние донаты:")
            for user, amount, anonymous in recent:
                who = "Аноним" if anonymous else (user.username or f"#{user.id}")
                print(f"    {who} — {amount} ₽")
    return 0


async def cmd_create(args: argparse.Namespace) -> int:
    deadline = None
    if args.days:
        deadline = _utcnow() + timedelta(days=args.days)
    async with session_factory() as session:
        goal = await goals.create_goal(
            session,
            title=args.title,
            target_rub=args.target,
            description=args.description,
            deadline=deadline,
        )
        if goal is None:
            print("Активная цель уже есть — закройте её: python -m app.cli.goals close")
            return 1
        print(f"Заведена цель #{goal.id}: {goal.title} на {goal.target_rub} ₽")
        if deadline:
            print(f"Срок: {deadline:%Y-%m-%d}")
        print("Опубликовать в канале: python -m app.cli.goals publish")
    return 0


async def cmd_publish(args: argparse.Namespace) -> int:
    chat_id = args.chat or settings.effective_goal_channel_id
    if not chat_id:
        print(
            "Канал не задан. Впишите GOAL_CHANNEL_ID в .env "
            "или передайте --chat -100..."
        )
        return 1
    async with session_factory() as session:
        goal = await goals.active_goal(session)
        if goal is None:
            print("Активной цели нет — публиковать нечего.")
            return 1
        if args.dry:
            raised = await goals.goal_progress(session, goal.id)
            recent = await goals.recent_donations(session, goal.id)
            print("--- пост будет выглядеть так ---")
            print(goal_post.render_post(goal, raised, recent))
            return 0
        if not await goal_post.publish(session, goal, chat_id):
            print(
                "Не удалось опубликовать. Обычно причина одна: бот не админ "
                "канала. Подробности — в журнале сервиса."
            )
            return 1
        print(f"Опубликовано: chat={goal.channel_chat_id} msg={goal.channel_message_id}")
    return 0


async def cmd_refresh() -> int:
    async with session_factory() as session:
        if await goal_post.refresh_active(session):
            print("Пост обновлён.")
            return 0
        print("Обновить не удалось: цели нет, пост не публиковался или Telegram отказал.")
        return 1


async def cmd_reopen() -> int:
    async with session_factory() as session:
        goal = await goals.reopen_goal(session)
        if goal is None:
            print("Вернуть нечего: закрытых целей нет либо уже идёт активная.")
            return 1
        raised = await goals.goal_progress(session, goal.id)
        print(f"Цель #{goal.id} «{goal.title}» снова в работе. Собрано {raised} ₽.")
        if goal.channel_message_id:
            print("Пост в канале сохранён — обновить: python -m app.cli.goals refresh")
    return 0


async def cmd_close() -> int:
    async with session_factory() as session:
        goal = await goals.active_goal(session)
        if goal is None:
            print("Активной цели нет.")
            return 1
        raised = await goals.goal_progress(session, goal.id)
        await goals.close_goal(session, goal)
        print(f"Цель #{goal.id} «{goal.title}» закрыта. Собрано {raised} из {goal.target_rub} ₽.")
        print("Донаты сохранены — они остаются в истории и в общем рейтинге.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Цели сбора пожертвований")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="показать активную цель и её прогресс")

    create = sub.add_parser("create", help="завести цель")
    create.add_argument("title", help="название, например «Новый сервер»")
    create.add_argument("target", type=int, help="сколько собрать, в рублях")
    create.add_argument("--description", default=None, help="пояснение под заголовком")
    create.add_argument("--days", type=int, default=None, help="срок сбора в днях")

    publish = sub.add_parser("publish", help="опубликовать пост в канале")
    publish.add_argument("--chat", type=int, default=None, help="id канала (по умолчанию из .env)")
    publish.add_argument("--dry", action="store_true", help="показать текст, ничего не отправляя")

    sub.add_parser("refresh", help="перерисовать опубликованный пост")
    sub.add_parser("close", help="закрыть активную цель")
    sub.add_parser("reopen", help="вернуть в работу последнюю закрытую цель")

    args = parser.parse_args()
    if args.command == "list":
        return asyncio.run(cmd_list())
    if args.command == "create":
        return asyncio.run(cmd_create(args))
    if args.command == "publish":
        return asyncio.run(cmd_publish(args))
    if args.command == "refresh":
        return asyncio.run(cmd_refresh())
    if args.command == "close":
        return asyncio.run(cmd_close())
    if args.command == "reopen":
        return asyncio.run(cmd_reopen())
    return 1


if __name__ == "__main__":
    sys.exit(main())

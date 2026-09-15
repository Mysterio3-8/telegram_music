"""Напоминания «Premium можно продлить бесплатно» (владелец 15.09: «чтобы больше
было взаимодействий»).

Кому и когда — по дате окончания Premium, три окна, каждое шириной в сутки
(таймер запускается раз в сутки, поэтому каждое окно ловится один раз):
  ends_in_4     — до конца осталось от 3 до 4 суток (середина пробной недели);
  ends_tomorrow — осталось меньше суток;
  ended         — закончился за последние сутки.
В сообщении — сколько друзей до ближайшей награды и ближайшее достижение с
днями Premium, плюс кнопки «Поделиться ссылкой» и «Открыть плеер».

Не пишем: админам, заблокировавшим бота, подпискам с автопродлением (им не
грозит окончание). Одно сообщение на человека, вид и дату окончания —
`user_reminders`; повторный запуск таймера не дублирует.

comeback — разовое «давно не виделись» тем, кто без Premium и молчит от 30 до
180 дней (владелец 16.09: «должно быть редким — вот если 30 дней пройдёт») (замер 15.09: удержание через сутки 9%, через неделю 3%, а напоминания
выше доходят только до людей с Premium). Не взявшим пробную неделю — про неё,
остальным — «напишите название трека» и строка про друзей. Один раз за всю
жизнь аккаунта, не больше COMEBACK_LIMIT (30) за ночь: старше полугода не
трогаем — человек нас уже забыл, и сообщение выглядит спамом.
"""
import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import AnalyticsEvent, FunnelEvent, SearchQuery, TrackEvent, User, UserReminder
from app.i18n import t
from app.services.bot_api import BotApiError
from app.services.gamification import (
    TRIAL_DAYS,
    build_achievements,
    collect_user_stats,
    count_referrals,
    next_referral_reward,
    referral_link,
)
from app.services.users import is_admin, user_language

logger = logging.getLogger(__name__)

KINDS = ("ends_in_4", "ends_tomorrow", "ended", "comeback")
COMEBACK_AFTER = timedelta(days=30)
COMEBACK_WINDOW = timedelta(days=180)
COMEBACK_LIMIT = 30  # потолок сообщений за ночь: владелец 16.09 — «главное не спамить»
COMEBACK_ANCHOR = "once"
SEND_PAUSE_SECONDS = 0.05  # Telegram держит ~30 сообщений в секунду — с запасом
_BLOCKED_MARKERS = ("bot was blocked", "user is deactivated", "chat not found")


@dataclass
class ReminderReport:
    due: int = 0
    sent: int = 0
    blocked: int = 0
    failed: int = 0
    by_kind: dict[str, int] = field(default_factory=dict)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def reminder_kind(user: User, now: datetime) -> str | None:
    if user.premium_until is None:
        return None
    days_left = (user.premium_until - now).total_seconds() / 86400
    if 3 < days_left <= 4:
        return "ends_in_4"
    if 0 < days_left <= 1:
        return "ends_tomorrow"
    if -1 < days_left <= 0:
        return "ended"
    return None


def _keyboard(lang: str, link: str) -> dict:
    share_url = f"https://t.me/share/url?url={quote(link, safe='')}&text={quote(t('remind.share_text', lang), safe='')}"
    keyboard = [[{"text": t("remind.share_button", lang), "url": share_url}]]
    if settings.public_base_url:
        keyboard.append([{"text": t("remind.open_player", lang), "web_app": {"url": settings.public_base_url}}])
    return {"inline_keyboard": keyboard}


async def _compose_comeback(session: AsyncSession, user: User) -> tuple[str, dict]:
    lang = user_language(user)
    link = referral_link(user.telegram_id, settings.bot_username)
    if not user.trial_used:
        lines = [t("remind.comeback_trial", lang, days=TRIAL_DAYS)]
    else:
        lines = [t("remind.comeback", lang)]
        friends, reward = next_referral_reward(await count_referrals(session, user.telegram_id))
        if friends and reward:
            lines.append(t("remind.referral_line", lang, friends=friends, days=reward, link=link))
    return "\n\n".join(lines), _keyboard(lang, link)


async def compose_reminder(session: AsyncSession, user: User, kind: str, now: datetime) -> tuple[str, dict]:
    if kind == "comeback":
        return await _compose_comeback(session, user)
    lang = user_language(user)
    days_left = max(1, round((user.premium_until - now).total_seconds() / 86400))
    lines = [t(f"remind.{kind}", lang, days=days_left)]

    invited = await count_referrals(session, user.telegram_id)
    link = referral_link(user.telegram_id, settings.bot_username)
    friends, reward = next_referral_reward(invited)
    if friends and reward:
        lines.append(t("remind.referral_line", lang, friends=friends, days=reward, link=link))

    stats = await collect_user_stats(session, user, invited=invited)
    pending = [a for a in build_achievements(stats) if not a.unlocked and a.reward_days > 0]
    if pending:
        nearest = max(pending, key=lambda a: (a.progress / a.target, -a.target))
        lines.append(
            t(
                "remind.achievement_line",
                lang,
                title=nearest.title,
                progress=nearest.progress,
                target=nearest.target,
                days=nearest.reward_days,
            )
        )

    return "\n\n".join(lines), _keyboard(lang, link)


async def due_reminders(session: AsyncSession, now: datetime) -> list[tuple[User, str, str]]:
    users = await session.scalars(
        select(User).where(
            User.premium_until.is_not(None),
            User.premium_until > now - timedelta(days=1),
            User.premium_until <= now + timedelta(days=4),
            User.bot_blocked.is_not(True),
        )
    )
    result = []
    for user in users.all():
        kind = reminder_kind(user, now)
        if kind is None or is_admin(user.telegram_id):
            continue
        if kind != "ended" and getattr(user, "autorenew", False) and getattr(user, "pay_method_id", None):
            continue
        anchor = user.premium_until.date().isoformat()
        already = await session.scalar(
            select(UserReminder.id).where(
                UserReminder.user_id == user.id,
                UserReminder.kind == kind,
                UserReminder.anchor == anchor,
            )
        )
        if already is None:
            result.append((user, kind, anchor))
    return result


async def last_activity(session: AsyncSession, since: datetime) -> dict[int, datetime]:
    """Последнее действие человека по всем журналам (напоминания бота — не действие)."""
    latest: dict[int, datetime] = {}
    queries = [
        select(model.user_id, func.max(model.created_at)).where(model.created_at >= since).group_by(model.user_id)
        for model in (TrackEvent, SearchQuery, FunnelEvent)
    ]
    queries.append(
        select(AnalyticsEvent.user_id, func.max(AnalyticsEvent.created_at))
        .where(
            AnalyticsEvent.created_at >= since,
            AnalyticsEvent.user_id.is_not(None),
            AnalyticsEvent.source != "system",
        )
        .group_by(AnalyticsEvent.user_id)
    )
    for query in queries:
        for user_id, at in (await session.execute(query)).all():
            if at is not None and (user_id not in latest or at > latest[user_id]):
                latest[user_id] = at
    return latest


async def due_comebacks(session: AsyncSession, now: datetime) -> list[tuple[User, str, str]]:
    already = select(UserReminder.user_id).where(UserReminder.kind == "comeback")
    users = (
        await session.scalars(
            select(User).where(
                User.bot_blocked.is_not(True),
                User.created_at <= now - COMEBACK_AFTER,
                # Premium идёт или закончился за последние сутки — у тех свои напоминания
                (User.premium_until.is_(None)) | (User.premium_until <= now - timedelta(days=1)),
                User.id.not_in(already),
            )
        )
    ).all()
    # Окно шире 30 дней: человек, активный 31 день назад, иначе считался бы «молчащим с регистрации»
    activity = await last_activity(session, now - COMEBACK_WINDOW - timedelta(days=1))
    candidates = []
    for user in users:
        if is_admin(user.telegram_id):
            continue
        last = activity.get(user.id)
        if last is None:
            last = user.created_at if user.created_at >= now - COMEBACK_WINDOW else None
        if last is not None and now - COMEBACK_WINDOW <= last <= now - COMEBACK_AFTER:
            candidates.append((last, user))
    # Сперва недавно пропавших: их вернуть проще всего
    candidates.sort(key=lambda item: item[0], reverse=True)
    return [(user, "comeback", COMEBACK_ANCHOR) for _last, user in candidates[:COMEBACK_LIMIT]]


async def send_due_reminders(
    session: AsyncSession, bot, *, now: datetime | None = None, dry: bool = False
) -> ReminderReport:
    now = now or _utcnow()
    report = ReminderReport()
    due = await due_reminders(session, now) + await due_comebacks(session, now)
    for user, kind, anchor in due:
        report.due += 1
        report.by_kind[kind] = report.by_kind.get(kind, 0) + 1
        text, markup = await compose_reminder(session, user, kind, now)
        if dry:
            continue
        try:
            await bot.send_message(user.telegram_id, text, reply_markup=markup)
        except BotApiError as error:
            description = str(error).lower()
            if any(marker in description for marker in _BLOCKED_MARKERS):
                user.bot_blocked = True
                report.blocked += 1
            else:
                report.failed += 1
                logger.warning("Напоминание не ушло user=%s: %s", user.id, error)
                continue  # временный сбой — попробуем на следующем запуске
        else:
            report.sent += 1
        session.add(UserReminder(user_id=user.id, kind=kind, anchor=anchor))
        if not user.bot_blocked:
            from app.services.analytics import build_event

            session.add(build_event("reminder_sent", source="system", user_id=user.id, props={"kind": kind}))
        await session.commit()
        await asyncio.sleep(SEND_PAUSE_SECONDS)
    return report

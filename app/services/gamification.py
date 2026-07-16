"""Геймификация (доп. ТЗ): рефералы, ранги, награды за приглашения, достижения.

Ранги и достижения — чистые функции от статистики. Реферальные Premium-награды
выдаются идемпотентно по счётчику referral_milestones_claimed на пользователе.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Playlist, Track, TrackEvent, User, UserLibrary

LIFETIME_DAYS = 36500  # «пожизненный» Premium
REFERRER_DISCOUNT_PCT = 50

# (порог приглашённых, дней Premium в награду) — по возрастанию
REFERRAL_MILESTONES: list[tuple[int, int]] = [
    (1, 3),
    (3, 10),
    (5, 30),
    (10, 60),
    (25, 180),
    (100, LIFETIME_DAYS),
]

# (порог, ключ, название, эмодзи) — по возрастанию
RANKS: list[tuple[int, str, str, str]] = [
    (1, "bronze", "Bronze", "🥉"),
    (5, "silver", "Silver", "🥈"),
    (15, "gold", "Gold", "🥇"),
    (50, "diamond", "Diamond", "💎"),
    (150, "legend", "Legend", "👑"),
]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ---------- Рефералы и ранги ----------


@dataclass(frozen=True)
class Rank:
    key: str
    title: str
    emoji: str
    threshold: int


@dataclass(frozen=True)
class RankProgress:
    current: Rank | None  # достигнутый ранг (None — ещё нет приглашённых)
    next: Rank | None  # следующий ранг (None — максимум)
    invited: int
    to_next: int  # сколько ещё приглашённых до следующего ранга


def referral_rank(invited: int) -> RankProgress:
    current: Rank | None = None
    nxt: Rank | None = None
    for threshold, key, title, emoji in RANKS:
        if invited >= threshold:
            current = Rank(key, title, emoji, threshold)
        elif nxt is None:
            nxt = Rank(key, title, emoji, threshold)
    to_next = (nxt.threshold - invited) if nxt else 0
    return RankProgress(current=current, next=nxt, invited=invited, to_next=to_next)


async def count_referrals(session: AsyncSession, telegram_id: int) -> int:
    count = await session.scalar(
        select(func.count()).select_from(User).where(User.referred_by == telegram_id)
    )
    return count or 0


async def register_referral(
    session: AsyncSession, user: User, referrer_telegram_id: int
) -> bool:
    """Привязывает нового пользователя к пригласившему. True — привязка выполнена.

    Игнорирует повторную привязку, самоприглашение и несуществующего реферера.
    """
    if user.referred_by is not None or referrer_telegram_id == user.telegram_id:
        return False
    referrer = await session.scalar(
        select(User).where(User.telegram_id == referrer_telegram_id)
    )
    if referrer is None:
        return False
    user.referred_by = referrer_telegram_id
    await session.commit()
    await grant_referral_milestones(session, referrer)
    return True


def _extend_premium(user: User, days: int) -> None:
    now = _utcnow()
    base = user.premium_until if (user.premium_until and user.premium_until > now) else now
    user.premium = True
    user.premium_until = base + timedelta(days=days)


async def grant_referral_milestones(session: AsyncSession, referrer: User) -> int:
    """Выдаёт Premium-дни за достигнутые пороги приглашений. Идемпотентно по
    referral_milestones_claimed. Возвращает число новых наград."""
    invited = await count_referrals(session, referrer.telegram_id)
    granted = 0
    while referrer.referral_milestones_claimed < len(REFERRAL_MILESTONES):
        threshold, days = REFERRAL_MILESTONES[referrer.referral_milestones_claimed]
        if invited < threshold:
            break
        _extend_premium(referrer, days)
        referrer.referral_milestones_claimed += 1
        granted += 1
    if granted:
        await session.commit()
    return granted


async def grant_referrer_discount(session: AsyncSession, buyer: User) -> None:
    """Пригласивший получает скидку на следующий месяц, когда приглашённый купил Premium."""
    if buyer.referred_by is None:
        return
    referrer = await session.scalar(
        select(User).where(User.telegram_id == buyer.referred_by)
    )
    if referrer is None:
        return
    referrer.premium_discount_pct = REFERRER_DISCOUNT_PCT
    await session.commit()


def referral_link(telegram_id: int, bot_username: str) -> str:
    return f"https://t.me/{bot_username}?start=ref_{telegram_id}"


# ---------- Статистика и достижения ----------


@dataclass(frozen=True)
class UserStats:
    listens: int
    listen_hours: float
    streak_days: int
    favorites: int
    playlists: int
    invited: int
    has_premium_ever: bool
    premium_year: bool


async def _listen_streak(session: AsyncSession, user_id: int) -> int:
    """Самая длинная серия дней подряд с прослушиваниями."""
    rows = await session.scalars(
        select(TrackEvent.created_at).where(
            TrackEvent.user_id == user_id, TrackEvent.event == "listen"
        )
    )
    dates = sorted({dt.date() for dt in rows.all() if dt is not None})
    if not dates:
        return 0
    best = run = 1
    for prev, cur in zip(dates, dates[1:]):
        if (cur - prev).days == 1:
            run += 1
            best = max(best, run)
        else:
            run = 1
    return best


async def collect_user_stats(session: AsyncSession, user: User) -> UserStats:
    listens = await session.scalar(
        select(func.count())
        .select_from(TrackEvent)
        .where(TrackEvent.user_id == user.id, TrackEvent.event == "listen")
    ) or 0
    seconds = await session.scalar(
        select(func.coalesce(func.sum(Track.duration), 0))
        .select_from(TrackEvent)
        .join(Track, Track.id == TrackEvent.track_id)
        .where(TrackEvent.user_id == user.id, TrackEvent.event == "listen")
    ) or 0
    favorites = await session.scalar(
        select(func.count()).select_from(UserLibrary).where(UserLibrary.user_id == user.id)
    ) or 0
    playlists = await session.scalar(
        select(func.count()).select_from(Playlist).where(Playlist.user_id == user.id)
    ) or 0
    invited = await count_referrals(session, user.telegram_id)
    streak = await _listen_streak(session, user.id)

    has_premium_ever = user.premium_until is not None
    premium_year = (
        user.premium_until is not None
        and (user.premium_until - user.created_at).days >= 365
    )
    return UserStats(
        listens=listens,
        listen_hours=round(seconds / 3600, 1),
        streak_days=streak,
        favorites=favorites,
        playlists=playlists,
        invited=invited,
        has_premium_ever=has_premium_ever,
        premium_year=premium_year,
    )


@dataclass(frozen=True)
class Achievement:
    code: str
    emoji: str
    title: str
    category: str
    unlocked: bool
    progress: int
    target: int


def build_achievements(stats: UserStats) -> list[Achievement]:
    hours = int(stats.listen_hours)
    # (code, emoji, title, category, значение, цель)
    defs: list[tuple[str, str, str, str, int, int]] = [
        ("listen_100", "🎵", "Первые 100 прослушиваний", "Прослушивание", stats.listens, 100),
        ("listen_1000", "🎧", "1 000 прослушиваний", "Прослушивание", stats.listens, 1000),
        ("hours_100", "🔥", "100 часов музыки", "Прослушивание", hours, 100),
        ("hours_500", "⏳", "500 часов музыки", "Прослушивание", hours, 500),
        ("streak_7", "📅", "7 дней подряд", "Активность", stats.streak_days, 7),
        ("streak_30", "📅", "30 дней подряд", "Активность", stats.streak_days, 30),
        ("streak_100", "📅", "100 дней подряд", "Активность", stats.streak_days, 100),
        ("fav_100", "❤️", "100 треков в избранном", "Коллекция", stats.favorites, 100),
        ("playlist_1", "📂", "Первый плейлист", "Коллекция", stats.playlists, 1),
        ("playlist_10", "📂", "10 плейлистов", "Коллекция", stats.playlists, 10),
        ("premium_first", "💎", "Первый месяц Premium", "Premium", int(stats.has_premium_ever), 1),
        ("premium_year", "👑", "Один год Premium", "Premium", int(stats.premium_year), 1),
        ("invite_1", "🤝", "Первый приглашённый друг", "Сообщество", stats.invited, 1),
        ("invite_10", "🚀", "10 приглашённых друзей", "Сообщество", stats.invited, 10),
        ("invite_50", "🌍", "50 приглашённых друзей", "Сообщество", stats.invited, 50),
        ("invite_100", "🏆", "100 приглашённых друзей", "Сообщество", stats.invited, 100),
    ]
    return [
        Achievement(
            code=code,
            emoji=emoji,
            title=title,
            category=category,
            unlocked=value >= target,
            progress=min(value, target),
            target=target,
        )
        for code, emoji, title, category, value, target in defs
    ]

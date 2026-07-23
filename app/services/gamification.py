"""Геймификация (доп. ТЗ): рефералы, ранги, награды за приглашения, достижения.

Ранги и достижения — чистые функции от статистики. Реферальные Premium-награды
выдаются идемпотентно по счётчику referral_milestones_claimed на пользователе.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Playlist,
    Track,
    TrackEvent,
    Upload,
    User,
    UserAchievement,
    UserLibrary,
)

LIFETIME_DAYS = 36500  # «пожизненный» Premium
REFERRER_DISCOUNT_PCT = 50
TRIAL_DAYS = 3  # пробный Premium, один раз на аккаунт

# (порог приглашённых, дней Premium в награду) — по возрастанию.
# Первые пороги низкие: награда должна прийти быстро, иначе никто не зовёт друзей.
# «Навсегда» вынесено на 5000 друзей (решение владельца) — за 100 было слишком дёшево.
REFERRAL_MILESTONES: list[tuple[int, int]] = [
    (1, 7),
    (2, 7),
    (3, 14),
    (5, 30),
    (10, 60),
    (25, 120),
    (50, 180),
    (100, 365),
    (250, 365),
    (500, 730),
    (1000, 1095),
    (2500, 1825),
    (5000, LIFETIME_DAYS),
]

# (порог, ключ, название, эмодзи) — по возрастанию
RANKS: list[tuple[int, str, str, str]] = [
    (1, "bronze", "Bronze", "🥉"),
    (10, "silver", "Silver", "🥈"),
    (50, "gold", "Gold", "🥇"),
    (250, "platinum", "Platinum", "🏆"),
    (1000, "diamond", "Diamond", "💎"),
    (5000, "legend", "Legend", "👑"),
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


def next_referral_reward(invited: int) -> tuple[int, int]:
    """(сколько друзей ещё нужно, сколько дней Premium дадут) для ближайшего порога.
    (0, 0) — все пороги пройдены."""
    for threshold, days in REFERRAL_MILESTONES:
        if invited < threshold:
            return threshold - invited, days
    return 0, 0


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
    premium_forever: bool
    uploads: int
    artists: int  # сколько разных исполнителей в библиотеке
    downloads: int


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
    uploads = await session.scalar(
        select(func.count()).select_from(Upload).where(Upload.user_id == user.id)
    ) or 0
    artists = await session.scalar(
        select(func.count(func.distinct(func.lower(Track.artist))))
        .select_from(UserLibrary)
        .join(Track, Track.id == UserLibrary.track_id)
        .where(UserLibrary.user_id == user.id)
    ) or 0

    downloads = await session.scalar(
        select(func.count())
        .select_from(TrackEvent)
        .where(TrackEvent.user_id == user.id, TrackEvent.event == "download")
    ) or 0

    has_premium_ever = user.premium_until is not None
    premium_days = (user.premium_until - user.created_at).days if user.premium_until else 0
    return UserStats(
        listens=listens,
        listen_hours=round(seconds / 3600, 1),
        streak_days=streak,
        favorites=favorites,
        playlists=playlists,
        invited=invited,
        has_premium_ever=has_premium_ever,
        premium_year=premium_days >= 365,
        premium_forever=premium_days >= 3650,  # 10+ лет = «навсегда»
        uploads=uploads,
        artists=artists,
        downloads=downloads,
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
    reward_days: int  # сколько дней Premium даёт достижение


# Тиры достижений: (префикс, эмодзи, категория, шаблон названия, [(порог, дней Premium)]).
# Награды за приглашения выдаёт grant_referral_milestones (тут reward=0, чтобы не двоить).
# Всего ~100 достижений — длинная лестница целей удерживает и мягко продаёт Premium.
_TIER_SPECS: list[tuple[str, str, str, str, list[tuple[int, int]]]] = [
    ("listen", "🎵", "Прослушивание", "{n} прослушиваний", [
        (10, 1), (50, 2), (100, 3), (250, 5), (500, 7), (1000, 14),
        (2500, 20), (5000, 30), (10000, 45), (25000, 60), (50000, 90), (100000, 120),
    ]),
    ("hours", "🔥", "Прослушивание", "{n} часов музыки", [
        (1, 1), (5, 2), (10, 3), (25, 5), (50, 7), (100, 10),
        (250, 20), (500, 30), (1000, 45), (2000, 60), (5000, 90), (10000, 120),
    ]),
    ("streak", "📅", "Активность", "{n} дней подряд", [
        (3, 1), (7, 3), (14, 7), (30, 14), (60, 25), (100, 40),
        (180, 60), (365, 120), (500, 180), (1000, 365),
    ]),
    ("fav", "❤️", "Коллекция", "{n} треков в библиотеке", [
        (10, 1), (25, 2), (50, 3), (100, 5), (250, 10), (500, 20),
        (1000, 30), (2500, 45), (5000, 60), (10000, 90),
    ]),
    ("artists", "🎤", "Коллекция", "{n} разных исполнителей", [
        (5, 1), (10, 2), (25, 3), (50, 7), (100, 14), (250, 30), (500, 45), (1000, 60), (2500, 90),
    ]),
    ("playlist", "🗂", "Коллекция", "{n} плейлистов", [
        (1, 1), (3, 2), (5, 3), (10, 7), (25, 14), (50, 30), (100, 60), (250, 120),
    ]),
    ("upload", "⬆️", "Вклад", "{n} своих треков", [
        (1, 2), (5, 3), (10, 7), (25, 14), (50, 20), (100, 30),
        (250, 45), (500, 60), (1000, 90), (2500, 120), (5000, 180), (10000, 365),
    ]),
    ("download", "💾", "Вклад", "{n} скачиваний", [
        (10, 1), (50, 2), (100, 3), (250, 5), (500, 10), (1000, 20), (2500, 30), (5000, 45), (10000, 60),
    ]),
    ("invite", "🤝", "Сообщество", "{n} приглашённых друзей", [
        (1, 0), (3, 0), (5, 0), (10, 0), (25, 0), (50, 0),
        (100, 0), (250, 0), (500, 0), (1000, 0), (2500, 0), (5000, 0),
    ]),
]


def _metric(stats: UserStats, prefix: str) -> int:
    return {
        "listen": stats.listens,
        "hours": int(stats.listen_hours),
        "streak": stats.streak_days,
        "fav": stats.favorites,
        "artists": stats.artists,
        "playlist": stats.playlists,
        "upload": stats.uploads,
        "download": stats.downloads,
        "invite": stats.invited,
    }[prefix]


def build_achievements(stats: UserStats) -> list[Achievement]:
    result: list[Achievement] = []
    for prefix, emoji, category, template, tiers in _TIER_SPECS:
        value = _metric(stats, prefix)
        for threshold, reward_days in tiers:
            result.append(
                Achievement(
                    code=f"{prefix}_{threshold}",
                    emoji=emoji,
                    title=template.format(n=threshold),
                    category=category,
                    unlocked=value >= threshold,
                    progress=min(value, threshold),
                    target=threshold,
                    reward_days=reward_days,
                )
            )
    # Особые вехи Premium
    specials = [
        ("premium_first", "💎", "Первый Premium", stats.has_premium_ever),
        ("premium_year", "👑", "Год с Premium", stats.premium_year),
        ("premium_forever", "♾️", "Premium навсегда", stats.premium_forever),
    ]
    for code, emoji, title, done in specials:
        result.append(
            Achievement(
                code=code,
                emoji=emoji,
                title=title,
                category="Premium",
                unlocked=bool(done),
                progress=int(bool(done)),
                target=1,
                reward_days=0,
            )
        )
    return result


async def grant_achievement_rewards(session: AsyncSession, user: User) -> list[Achievement]:
    """Начисляет дни Premium за впервые открытые достижения.

    Награды за приглашения не дублируются здесь: их выдаёт grant_referral_milestones
    (у них свои пороги и суммы), поэтому reward_days у invite_* равны нулю.
    Идемпотентность — через уникальную пару (user_id, code) в user_achievements.
    """
    stats = await collect_user_stats(session, user)
    unlocked = [a for a in build_achievements(stats) if a.unlocked and a.reward_days > 0]
    if not unlocked:
        return []

    known = set(
        (
            await session.scalars(
                select(UserAchievement.code).where(UserAchievement.user_id == user.id)
            )
        ).all()
    )
    fresh = [a for a in unlocked if a.code not in known]
    if not fresh:
        return []

    for achievement in fresh:
        session.add(
            UserAchievement(
                user_id=user.id, code=achievement.code, granted_days=achievement.reward_days
            )
        )
        _extend_premium(user, achievement.reward_days)
    await session.commit()
    return fresh


async def start_trial(session: AsyncSession, user: User) -> bool:
    """Пробный Premium на TRIAL_DAYS дней — один раз на аккаунт.
    False — уже использован или Premium активен."""
    if user.trial_used:
        return False
    now = _utcnow()
    if user.premium and user.premium_until and user.premium_until > now:
        return False
    user.trial_used = True
    _extend_premium(user, TRIAL_DAYS)
    await session.commit()
    return True


@dataclass(frozen=True)
class TopArtist:
    name: str
    listens: int


async def top_artists(session: AsyncSession, user_id: int, limit: int = 5) -> list[TopArtist]:
    """Любимые исполнители пользователя по числу прослушиваний (профиль, скрины VK)."""
    rows = await session.execute(
        select(Track.artist, func.count().label("listens"))
        .select_from(TrackEvent)
        .join(Track, Track.id == TrackEvent.track_id)
        .where(TrackEvent.user_id == user_id, TrackEvent.event == "listen")
        .group_by(func.lower(Track.artist))
        .order_by(func.count().desc())
        .limit(limit)
    )
    return [TopArtist(name=name, listens=listens) for name, listens in rows.all()]


async def top_tracks(session: AsyncSession, user_id: int, limit: int = 5) -> list[Track]:
    """Самые прослушиваемые треки пользователя."""
    rows = await session.execute(
        select(Track, func.count().label("listens"))
        .select_from(TrackEvent)
        .join(Track, Track.id == TrackEvent.track_id)
        .where(TrackEvent.user_id == user_id, TrackEvent.event == "listen")
        .group_by(Track.id)
        .order_by(func.count().desc())
        .limit(limit)
    )
    return [track for track, _ in rows.all()]


@dataclass(frozen=True)
class LeaderRow:
    telegram_id: int
    name: str
    invited: int


async def referral_leaderboard(session: AsyncSession, limit: int = 10) -> list[LeaderRow]:
    """Топ пригласивших — соревнование заметно двигает рефералку."""
    rows = await session.execute(
        select(User.referred_by, func.count().label("invited"))
        .where(User.referred_by.is_not(None))
        .group_by(User.referred_by)
        .order_by(func.count().desc())
        .limit(limit)
    )
    pairs = rows.all()
    if not pairs:
        return []
    referrer_ids = [telegram_id for telegram_id, _ in pairs]
    names = {
        u.telegram_id: (u.first_name or u.username or "Аноним")
        for u in (
            await session.scalars(select(User).where(User.telegram_id.in_(referrer_ids)))
        ).all()
    }
    return [
        LeaderRow(telegram_id=telegram_id, name=names.get(telegram_id, "Аноним"), invited=invited)
        for telegram_id, invited in pairs
    ]

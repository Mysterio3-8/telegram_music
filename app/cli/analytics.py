"""Сводный отчёт аналитики: люди, прослушивания, жанры, настроения, поиск, деньги.

    python -m app.cli.analytics             # за 30 дней
    python -m app.cli.analytics --days 7

Владелец 15.09: «собирать очень много статистики — бизнес, прослушивания,
жанры, настроения — чтобы анализировать и улучшать». Отчёт читает то, что уже
пишется: track_events, search_queries, analytics_events, funnel_events,
payments, donations, user_reminders.

⚠️ Источник прослушивания (бот / Mini App / воркер) пишется с 15.09 — у более
ранних прослушиваний его нет, они попадают в «до разметки».
"""
import argparse
import asyncio
import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.db.base import session_factory
from app.db.models import (
    AnalyticsEvent,
    ArtistGenre,
    Donation,
    FunnelEvent,
    Genre,
    Payment,
    SearchQuery,
    Track,
    TrackEvent,
    User,
)


@dataclass
class AnalyticsReport:
    days: int
    users_total: int = 0
    users_new: int = 0
    active_1d: int = 0
    active_7d: int = 0
    active_window: int = 0
    retention_d1: tuple[int, int] = (0, 0)  # (вернулись, из скольких)
    retention_d7: tuple[int, int] = (0, 0)
    listens: int = 0
    listeners: int = 0
    listens_by_source: dict[str, int] = field(default_factory=dict)
    downloads: int = 0
    completes: int = 0
    skips: int = 0
    top_tracks: list[tuple[str, int]] = field(default_factory=list)
    top_genres: list[tuple[str, int]] = field(default_factory=list)
    moods: list[tuple[str, int]] = field(default_factory=list)
    searches: int = 0
    searches_with_count: int = 0
    searches_empty: int = 0
    top_queries: list[tuple[str, int]] = field(default_factory=list)
    payments_count: int = 0
    payments_rub: int = 0
    payments_stars: int = 0
    paying_users: int = 0
    donations_count: int = 0
    donations_rub: int = 0
    premium_active: int = 0
    trials_total: int = 0
    reminders_by_kind: dict[str, int] = field(default_factory=dict)
    reminders_returned: tuple[int, int] = (0, 0)  # (вернулись за 48 ч, отправлено)
    paywall_views: int = 0
    shares: int = 0
    app_opens: int = 0
    sessions: int = 0
    session_users: int = 0
    session_median_sec: int = 0
    session_avg_sec: int = 0


# Пауза дольше получаса между событиями Mini App — это уже новая сессия
SESSION_GAP = timedelta(minutes=30)


def split_sessions(times: list[datetime]) -> list[int]:
    """Длительности сессий в секундах по отсортированным меткам событий одного человека."""
    durations: list[int] = []
    start = prev = None
    for at in sorted(times):
        if prev is None or at - prev > SESSION_GAP:
            if start is not None:
                durations.append(int((prev - start).total_seconds()))
            start = at
        prev = at
    if start is not None:
        durations.append(int((prev - start).total_seconds()))
    return durations


def _short(text: str, limit: int = 60) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def _activity(session, since: datetime) -> list[tuple[int, datetime]]:
    rows: list[tuple[int, datetime]] = []
    for model in (TrackEvent, SearchQuery, FunnelEvent):
        result = await session.execute(
            select(model.user_id, model.created_at).where(model.created_at >= since)
        )
        rows.extend(result.all())
    result = await session.execute(
        select(AnalyticsEvent.user_id, AnalyticsEvent.created_at).where(
            AnalyticsEvent.created_at >= since,
            AnalyticsEvent.user_id.is_not(None),
            AnalyticsEvent.source != "system",  # напоминание — не действие человека
        )
    )
    rows.extend(result.all())
    return rows


def _count(rows, name: str) -> int:
    return sum(count for key, count in rows if key == name)


async def build_analytics_report(session, days: int, now: datetime | None = None) -> AnalyticsReport:
    now = now or _utcnow()
    since = now - timedelta(days=days)
    report = AnalyticsReport(days=days)

    report.users_total = await session.scalar(select(func.count()).select_from(User)) or 0
    report.users_new = await session.scalar(
        select(func.count()).select_from(User).where(User.created_at >= since)
    ) or 0

    history_since = now - timedelta(days=max(days, 38))
    activity = await _activity(session, history_since)
    report.active_1d = len({u for u, at in activity if at >= now - timedelta(days=1)})
    report.active_7d = len({u for u, at in activity if at >= now - timedelta(days=7)})
    report.active_window = len({u for u, at in activity if at >= since})

    # Удержание: из пришедших 8–38 дней назад — кто сделал хоть что-то спустя 1 и 7 суток
    cohort = (
        await session.execute(
            select(User.id, User.created_at).where(
                User.created_at >= now - timedelta(days=38), User.created_at <= now - timedelta(days=8)
            )
        )
    ).all()
    by_user: dict[int, list[datetime]] = {}
    for user_id, at in activity:
        by_user.setdefault(user_id, []).append(at)
    d1 = sum(1 for uid, joined in cohort if any(at >= joined + timedelta(days=1) for at in by_user.get(uid, [])))
    d7 = sum(1 for uid, joined in cohort if any(at >= joined + timedelta(days=7) for at in by_user.get(uid, [])))
    report.retention_d1 = (d1, len(cohort))
    report.retention_d7 = (d7, len(cohort))

    listen_filter = (TrackEvent.event == "listen", TrackEvent.created_at >= since)
    report.listens = await session.scalar(select(func.count()).select_from(TrackEvent).where(*listen_filter)) or 0
    report.listeners = await session.scalar(
        select(func.count(func.distinct(TrackEvent.user_id))).where(*listen_filter)
    ) or 0
    report.downloads = await session.scalar(
        select(func.count()).select_from(TrackEvent).where(
            TrackEvent.event == "download", TrackEvent.created_at >= since
        )
    ) or 0

    named = (
        await session.execute(
            select(AnalyticsEvent.name, AnalyticsEvent.source, func.count())
            .where(AnalyticsEvent.created_at >= since)
            .group_by(AnalyticsEvent.name, AnalyticsEvent.source)
        )
    ).all()
    by_source = {source: count for name, source, count in named if name == "listen"}
    marked = sum(by_source.values())
    if report.listens > marked:
        by_source["до разметки"] = report.listens - marked
    report.listens_by_source = dict(sorted(by_source.items(), key=lambda kv: -kv[1]))
    per_name = Counter()
    for name, _source, count in named:
        per_name[name] += count
    report.completes = per_name["play_complete"]
    report.skips = per_name["play_skip"]
    report.paywall_views = per_name["paywall_view"]
    report.shares = per_name["share_click"]
    report.app_opens = per_name["app_open"]

    # Сессии Mini App: все его события (включая серверный listen с source=miniapp).
    # Сессия из одного события длится 0 сек — открыл и закрыл, это тоже ответ.
    miniapp_rows = (
        await session.execute(
            select(AnalyticsEvent.user_id, AnalyticsEvent.created_at).where(
                AnalyticsEvent.source == "miniapp",
                AnalyticsEvent.created_at >= since,
                AnalyticsEvent.user_id.is_not(None),
            )
        )
    ).all()
    per_user_times: dict[int, list[datetime]] = {}
    for user_id, at in miniapp_rows:
        per_user_times.setdefault(user_id, []).append(at)
    durations = sorted(d for times in per_user_times.values() for d in split_sessions(times))
    report.sessions = len(durations)
    report.session_users = len(per_user_times)
    if durations:
        report.session_median_sec = durations[len(durations) // 2]
        report.session_avg_sec = sum(durations) // len(durations)

    report.top_tracks = [
        # Имена из источников бывают на 200 символов (замер прода 15.09) — режем,
        # иначе один мусорный трек съедает сообщение отчёта в Telegram
        (_short(f"{artist} — {title}"), count)
        for artist, title, count in (
            await session.execute(
                select(Track.artist, Track.title, func.count())
                .join(TrackEvent, TrackEvent.track_id == Track.id)
                .where(*listen_filter)
                .group_by(Track.id)
                .order_by(func.count().desc())
                .limit(10)
            )
        ).all()
    ]
    report.top_genres = [
        (name, count)
        for name, count in (
            await session.execute(
                select(Genre.name, func.count())
                .select_from(TrackEvent)
                .join(Track, Track.id == TrackEvent.track_id)
                .join(ArtistGenre, ArtistGenre.artist_id == Track.artist_id)
                .join(Genre, Genre.id == ArtistGenre.genre_id)
                .where(*listen_filter)
                .group_by(Genre.id)
                .order_by(func.count().desc())
                .limit(10)
            )
        ).all()
    ]
    report.moods = [
        (mood or "не размечено", count)
        for mood, count in (
            await session.execute(
                select(Track.mood, func.count())
                .join(TrackEvent, TrackEvent.track_id == Track.id)
                .where(*listen_filter)
                .group_by(Track.mood)
                .order_by(func.count().desc())
            )
        ).all()
    ]

    report.searches = await session.scalar(
        select(func.count()).select_from(SearchQuery).where(SearchQuery.created_at >= since)
    ) or 0
    search_props = (
        await session.scalars(
            select(AnalyticsEvent.props).where(
                AnalyticsEvent.name == "search", AnalyticsEvent.created_at >= since
            )
        )
    ).all()
    for raw in search_props:
        try:
            results = json.loads(raw).get("results") if raw else None
        except ValueError:
            results = None
        if isinstance(results, int):
            report.searches_with_count += 1
            report.searches_empty += results == 0
    report.top_queries = [
        (query, count)
        for query, count in (
            await session.execute(
                select(func.min(SearchQuery.query), func.count())
                .where(SearchQuery.created_at >= since)
                .group_by(func.lower(SearchQuery.query))
                .order_by(func.count().desc())
                .limit(10)
            )
        ).all()
    ]

    pay = (
        await session.execute(
            select(
                func.count(),
                func.coalesce(func.sum(Payment.amount_rub), 0),
                func.coalesce(func.sum(Payment.amount_stars), 0),
                func.count(func.distinct(Payment.user_id)),
            ).where(Payment.created_at >= since)
        )
    ).one()
    report.payments_count, report.payments_rub, report.payments_stars, report.paying_users = (
        int(pay[0]), int(pay[1]), int(pay[2]), int(pay[3])
    )
    don = (
        await session.execute(
            select(func.count(), func.coalesce(func.sum(Donation.amount_rub), 0)).where(
                Donation.created_at >= since, Donation.refunded_at.is_(None)
            )
        )
    ).one()
    report.donations_count, report.donations_rub = int(don[0]), int(don[1])
    report.premium_active = await session.scalar(
        select(func.count()).select_from(User).where(User.premium_until > now)
    ) or 0
    report.trials_total = await session.scalar(
        select(func.count()).select_from(User).where(User.trial_used.is_(True))
    ) or 0

    reminders = (
        await session.execute(
            select(AnalyticsEvent.user_id, AnalyticsEvent.created_at, AnalyticsEvent.props).where(
                AnalyticsEvent.name == "reminder_sent", AnalyticsEvent.created_at >= since
            )
        )
    ).all()
    kinds = Counter()
    returned = 0
    for user_id, sent_at, raw in reminders:
        try:
            kinds[json.loads(raw).get("kind", "?") if raw else "?"] += 1
        except ValueError:
            kinds["?"] += 1
        if any(sent_at < at <= sent_at + timedelta(hours=48) for at in by_user.get(user_id, [])):
            returned += 1
    report.reminders_by_kind = dict(kinds)
    report.reminders_returned = (returned, len(reminders))
    return report


def _pct(part: int, whole: int) -> str:
    return f"{part * 100 // whole}%" if whole else "—"


def _mins(seconds: int) -> str:
    return f"{seconds // 60} мин {seconds % 60} сек"


CSV_COLUMNS = ("created_at", "name", "source", "user_id", "track_id", "props")


async def export_events_csv(session, days: int, path: str, now: datetime | None = None) -> int:
    """Сырые события аналитики за окно — в CSV для таблиц. user_id внутренний, не Telegram."""
    import csv

    since = (now or _utcnow()) - timedelta(days=days)
    rows = (
        await session.execute(
            select(*(getattr(AnalyticsEvent, c) for c in CSV_COLUMNS))
            .where(AnalyticsEvent.created_at >= since)
            .order_by(AnalyticsEvent.created_at)
        )
    ).all()
    # utf-8-sig: Excel иначе показывает кириллицу в props кракозябрами
    with open(path, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(CSV_COLUMNS)
        writer.writerows(rows)
    return len(rows)


TELEGRAM_LIMIT = 4000


def split_message(text: str, limit: int = TELEGRAM_LIMIT) -> list[str]:
    """Режем по строкам: у Telegram потолок 4096 символов на сообщение."""
    chunks: list[str] = []
    current = ""
    for line in text.split("\n"):
        line = line[:limit]
        if current and len(current) + 1 + len(line) > limit:
            chunks.append(current)
            current = line
        else:
            current = f"{current}\n{line}" if current else line
    if current:
        chunks.append(current)
    return chunks


def format_report(r: AnalyticsReport) -> str:
    lines = [
        f"=== Аналитика за {r.days} дн. ===",
        "",
        "ЛЮДИ",
        f"  всего {r.users_total}, новых {r.users_new}",
        f"  активны: сутки {r.active_1d}, неделя {r.active_7d}, окно {r.active_window}",
        f"  удержание (пришли 8–38 дн. назад): через сутки {r.retention_d1[0]}/{r.retention_d1[1]} "
        f"({_pct(*r.retention_d1)}), через неделю {r.retention_d7[0]}/{r.retention_d7[1]} ({_pct(*r.retention_d7)})",
        "",
        "ПРОСЛУШИВАНИЯ",
        f"  {r.listens} прослушиваний у {r.listeners} человек, скачиваний {r.downloads}",
        f"  по источникам: {r.listens_by_source or '—'}",
        f"  Mini App: открытий {r.app_opens}, сессий {r.sessions} у {r.session_users} человек, "
        f"длина медиана {_mins(r.session_median_sec)}, в среднем {_mins(r.session_avg_sec)}",
        f"  Mini App: дослушали {r.completes}, пропустили {r.skips} ({_pct(r.skips, r.completes + r.skips)} пропусков)",
        "  топ треков: " + ("; ".join(f"{n} ×{c}" for n, c in r.top_tracks) or "—"),
        "  жанры: " + (", ".join(f"{n} {c}" for n, c in r.top_genres) or "—"),
        "  настроения: " + (", ".join(f"{n} {c}" for n, c in r.moods) or "—"),
        "",
        "ПОИСК",
        f"  запросов {r.searches}; с числом результатов {r.searches_with_count}, "
        f"пустых {r.searches_empty} ({_pct(r.searches_empty, r.searches_with_count)})",
        "  топ запросов: " + (", ".join(f"«{q}» ×{c}" for q, c in r.top_queries) or "—"),
        "",
        "ДЕНЬГИ И РОСТ",
        f"  оплат {r.payments_count} на {r.payments_rub} ₽ и {r.payments_stars} ⭐ от {r.paying_users} человек",
        f"  донатов {r.donations_count} на {r.donations_rub} ₽",
        f"  Premium активен у {r.premium_active}; пробный период брали {r.trials_total} "
        f"(платящих из них по окну — {_pct(r.paying_users, r.trials_total)})",
        f"  пэйвол показан {r.paywall_views} раз, «поделиться» нажато {r.shares}",
        f"  напоминания: {r.reminders_by_kind or '—'}; вернулись за 48 ч "
        f"{r.reminders_returned[0]}/{r.reminders_returned[1]} ({_pct(*r.reminders_returned)})",
    ]
    return "\n".join(lines)


async def _main(days: int, csv_path: str | None, send: bool) -> int:
    async with session_factory() as session:
        report = await build_analytics_report(session, days)
        if csv_path:
            count = await export_events_csv(session, days, csv_path)
            print(f"CSV: {count} событий → {csv_path}")
    text = format_report(report)
    print(text)
    if not send:
        return 0
    from app.config import settings
    from app.services.telegram_send import send_message

    chat_id = settings.health_alert_id
    if chat_id is None:
        print("Отправка: не задан ни HEALTH_ALERT_CHAT, ни ADMIN_IDS")
        return 1
    for chunk in split_message(f"📊 {text}"):
        if not await send_message(chat_id, chunk):
            print("Отправка в Telegram не удалась — подробности в журнале")
            return 1
    print(f"Отчёт отправлен в чат {chat_id}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--csv", metavar="PATH", help="выгрузить сырые события за окно в CSV")
    parser.add_argument("--send", action="store_true", help="отправить отчёт дежурному админу в Telegram")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_main(args.days, args.csv, args.send)))


if __name__ == "__main__":
    main()

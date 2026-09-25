"""Сводный отчёт аналитики (python -m app.cli.analytics) и приём событий Mini App."""
from datetime import datetime, timedelta

import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.app import create_app
from app.api.deps import get_db
from app.api.security import create_access_token
from app.cli.analytics import (
    build_analytics_report,
    export_events_csv,
    format_report,
    split_message,
    split_sessions,
)
from app.db import models  # noqa: F401
from app.db.base import Base
from app.db.models import (
    AnalyticsEvent,
    Artist,
    ArtistGenre,
    Genre,
    Payment,
    SearchQuery,
    Track,
    TrackEvent,
    User,
)
from app.services.analytics import build_event

NOW = datetime(2026, 9, 15, 12, 0, 0)


async def test_report_counts_people_listens_genres_moods_and_money(session):
    artist = Artist(name="Kizaru", normalized_name="kizaru")
    genre = Genre(name="Хип-хоп", slug="hip-hop")
    session.add_all([artist, genre])
    await session.flush()
    session.add(ArtistGenre(artist_id=artist.id, genre_id=genre.id))
    track = Track(title="Fake ID", artist="Kizaru", artist_id=artist.id, duration=150, mood="energetic")
    old = User(telegram_id=1, created_at=NOW - timedelta(days=20))
    new = User(telegram_id=2, created_at=NOW - timedelta(hours=5), trial_used=True,
               premium=True, premium_until=NOW + timedelta(days=6))
    session.add_all([track, old, new])
    await session.flush()
    session.add_all(
        [
            TrackEvent(user_id=old.id, track_id=track.id, event="listen", created_at=NOW - timedelta(days=12)),
            TrackEvent(user_id=old.id, track_id=track.id, event="listen", created_at=NOW - timedelta(hours=2)),
            TrackEvent(user_id=new.id, track_id=track.id, event="listen", created_at=NOW - timedelta(hours=1)),
            build_event("listen", source="miniapp", user_id=new.id, track_id=track.id),
            build_event("play_skip", source="miniapp", user_id=new.id, track_id=track.id, props={"position_pct": 20}),
            build_event("search", source="bot", user_id=old.id, props={"results": 0}),
            build_event("search", source="bot", user_id=old.id, props={"results": 12}),
            SearchQuery(user_id=old.id, query="кизару", created_at=NOW - timedelta(hours=3)),
            Payment(user_id=new.id, amount_rub=49, source="yookassa", created_at=NOW - timedelta(hours=1)),
        ]
    )
    await session.commit()
    for event in (await session.scalars(select(AnalyticsEvent))).all():
        event.created_at = NOW - timedelta(hours=1)
    await session.commit()

    report = await build_analytics_report(session, days=30, now=NOW)
    assert (report.users_total, report.users_new) == (2, 2)  # оба пришли в пределах 30 дней
    assert report.active_1d == 2
    assert report.retention_d1 == (1, 1)  # старый вернулся спустя сутки
    assert report.listens == 3 and report.listeners == 2
    assert report.listens_by_source == {"до разметки": 2, "miniapp": 1}
    assert report.skips == 1 and report.completes == 0
    assert report.top_genres == [("Хип-хоп", 3)]
    assert report.moods == [("energetic", 3)]
    assert (report.searches_with_count, report.searches_empty) == (2, 1)
    assert (report.payments_count, report.payments_rub, report.paying_users) == (1, 49, 1)
    assert report.premium_active == 1 and report.trials_total == 1
    text = format_report(report)
    assert "Хип-хоп 3" in text and "пустых 1 (50%)" in text


def test_split_sessions_by_half_hour_gap():
    t = NOW
    times = [t, t + timedelta(minutes=5), t + timedelta(minutes=20), t + timedelta(hours=2)]
    assert split_sessions(times) == [20 * 60, 0]
    assert split_sessions([]) == []


def test_split_message_respects_telegram_limit():
    text = "\n".join(["x" * 30] * 400)
    chunks = split_message(text, limit=1000)
    assert all(len(c) <= 1000 for c in chunks)
    assert "\n".join(chunks) == text


async def test_report_sessions_and_csv_export(session, tmp_path):
    user = User(telegram_id=7, created_at=NOW - timedelta(days=2))
    session.add(user)
    await session.flush()
    stamps = [("app_open", 0), ("screen_view", 3), ("play_complete", 9), ("app_open", 120)]
    events = [build_event(name, source="miniapp", user_id=user.id, props={"screen": "дом"}) for name, _ in stamps]
    session.add_all(events)
    await session.commit()
    for event, (_, minutes) in zip(events, stamps):
        event.created_at = NOW - timedelta(hours=3) + timedelta(minutes=minutes)
    await session.commit()

    report = await build_analytics_report(session, days=7, now=NOW)
    assert report.app_opens == 2
    assert (report.sessions, report.session_users) == (2, 1)
    assert report.session_avg_sec == 9 * 60 // 2
    assert "сессий 2 у 1" in format_report(report)

    path = tmp_path / "events.csv"
    assert await export_events_csv(session, 7, str(path), now=NOW) == 4
    content = path.read_text(encoding="utf-8-sig")
    assert content.splitlines()[0] == "created_at,name,source,user_id,track_id,props"
    assert "дом" in content


@pytest_asyncio.fixture
async def api():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as seed:
        seed.add(User(telegram_id=556, first_name="Free"))
        await seed.commit()

    async def override_get_db():
        async with factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app), factory
    app.dependency_overrides.clear()
    await engine.dispose()


async def test_miniapp_events_accept_only_client_names_without_premium(api):
    client, factory = api
    auth = {"Authorization": f"Bearer {create_access_token(556)}"}
    body = {
        "events": [
            {"name": "paywall_view"},
            {"name": "screen_view", "props": {"screen": "home"}},
            {"name": "listen", "track_id": 1},  # серверное — из браузера не принимаем
            {"name": "play_skip", "track_id": -5, "props": {"position_pct": 30}},  # минус — не трек
        ]
    }
    assert client.post("/analytics/events", headers=auth, json=body).status_code == 204
    async with factory() as session:
        rows = (await session.execute(select(AnalyticsEvent.name, AnalyticsEvent.source, AnalyticsEvent.track_id))).all()
    assert sorted(rows) == [("paywall_view", "miniapp", None), ("play_skip", "miniapp", None), ("screen_view", "miniapp", None)]

    too_many = {"events": [{"name": "screen_view"}] * 51}
    assert client.post("/analytics/events", headers=auth, json=too_many).status_code == 422
    assert client.post("/analytics/events", json=body).status_code in (401, 403)


def test_report_has_no_raw_dicts():
    """Прогон 25.09: владелец видел «{'bot': 62, 'worker': 54}» в отчёте."""
    from app.cli.analytics import AnalyticsReport, format_report

    report = AnalyticsReport(days=7)
    report.listens_by_source.update({"bot": 62, "worker": 54, "miniapp": 33})
    report.reminders_by_kind.update({"comeback": 3})
    text = format_report(report)
    assert "{" not in text
    assert "в боте 62, выдача поиска 54, Mini App 33" in text
    assert "«вернись» 3" in text

"""Веб-админка: данные для страницы в браузере владельца (16.09).

Живёт НА СЕРВЕРЕ и слушает только 127.0.0.1 — из интернета её не видно вовсе,
в nginx она не заведена. Владелец открывает её на своём компьютере через
SSH-туннель (`python -m app.webadmin`), то есть пропуск — его SSH-ключ.

Почему так, а не «страница на домене с паролем»: в логах домена 2014 путей
сканеров за одну ротацию. Страница, которой нет в интернете, не имеет поверхности
атаки вообще — ни брутфорса, ни утечки пароля, ни забытой сессии в чужом браузере.

Второй рубеж на случай, если туннель прокинут неаккуратно: заголовок
`X-Admin-Token` сверяется с `WEBADMIN_TOKEN` из .env, когда тот задан.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cli.analytics import build_analytics_report
from app.config import settings
from app.db.base import session_factory
from app.db.models import Donation, Payment, Track, TrackEvent, User
from app.services.donations import donations_summary
from app.services.revenue import collect_revenue
from app.services.search_index import normalize_search_query
from app.services.track_lookup.ranking import to_latin
from app.services.stats import collect_stats

UI_DIR = Path(__file__).resolve().parents[2] / "webadmin"


async def get_session() -> AsyncSession:
    async with session_factory() as session:
        yield session


async def check_token(x_admin_token: str | None = Header(default=None)) -> None:
    expected = getattr(settings, "webadmin_token", "") or ""
    if expected and x_admin_token != expected:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный токен админки")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def create_app() -> FastAPI:
    app = FastAPI(title="Infinity Music — админка", docs_url=None, redoc_url=None)

    @app.get("/api/overview")
    async def overview(
        days: int = Query(default=30, ge=1, le=365),
        session: AsyncSession = Depends(get_session),
        _: None = Depends(check_token),
    ) -> dict:
        report = await build_analytics_report(session, days)
        stats = await collect_stats(session)
        revenue = await collect_revenue(session)
        donations_rub, donations_count = await donations_summary(session)
        # Ряд по дням для графиков: прослушивания и новые люди
        since = _utcnow() - timedelta(days=days)
        listens_by_day = dict(
            (
                await session.execute(
                    select(func.date(TrackEvent.created_at), func.count())
                    .where(TrackEvent.event == "listen", TrackEvent.created_at >= since)
                    .group_by(func.date(TrackEvent.created_at))
                )
            ).all()
        )
        users_by_day = dict(
            (
                await session.execute(
                    select(func.date(User.created_at), func.count())
                    .where(User.created_at >= since)
                    .group_by(func.date(User.created_at))
                )
            ).all()
        )
        series = []
        for offset in range(days, -1, -1):
            day = (_utcnow() - timedelta(days=offset)).date().isoformat()
            series.append(
                {"day": day, "listens": listens_by_day.get(day, 0), "users": users_by_day.get(day, 0)}
            )
        return {
            "days": days,
            "report": report.__dict__,
            "catalog": stats.__dict__,
            "revenue": revenue.__dict__,
            "donations": {"count": donations_count, "rub": donations_rub},
            "series": series,
        }

    @app.get("/api/users")
    async def users(
        q: str = Query(default=""),
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
        session: AsyncSession = Depends(get_session),
        _: None = Depends(check_token),
    ) -> dict:
        query = select(User)
        needle = q.strip()
        if needle:
            like = f"%{needle.lower()}%"
            # ⚠️ SQLite lower() не понижает кириллицу — имена сравниваем как есть
            # и дополнительно по уже понижённой строке; id ищем точным совпадением
            conditions = [func.lower(User.first_name).like(like), func.lower(User.username).like(like)]
            for variant in {needle, needle.lower(), needle.capitalize(), needle.title()}:
                conditions.append(User.first_name.like(f"%{variant}%"))
                conditions.append(User.username.like(f"%{variant}%"))
            if needle.isdigit():
                conditions.append(User.telegram_id == int(needle))
            query = query.where(or_(*conditions))
        total = await session.scalar(select(func.count()).select_from(query.subquery())) or 0
        rows = (await session.scalars(query.order_by(User.created_at.desc()).limit(limit).offset(offset))).all()
        listens = dict(
            (
                await session.execute(
                    select(TrackEvent.user_id, func.count())
                    .where(TrackEvent.event == "listen", TrackEvent.user_id.in_([u.id for u in rows] or [0]))
                    .group_by(TrackEvent.user_id)
                )
            ).all()
        )
        now = _utcnow()
        return {
            "total": total,
            "items": [
                {
                    "id": u.id,
                    "telegram_id": u.telegram_id,
                    "name": u.first_name or u.username or "—",
                    "username": u.username,
                    "created_at": u.created_at.isoformat() if u.created_at else None,
                    "premium_until": u.premium_until.isoformat() if u.premium_until else None,
                    "premium_active": bool(u.premium_until and u.premium_until > now),
                    "trial_used": bool(u.trial_used),
                    "blocked": bool(u.bot_blocked),
                    "listens": listens.get(u.id, 0),
                    "language": u.ui_language or u.language or "—",
                }
                for u in rows
            ],
        }

    @app.get("/api/tracks")
    async def tracks(
        q: str = Query(default=""),
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
        session: AsyncSession = Depends(get_session),
        _: None = Depends(check_token),
    ) -> dict:
        query = select(Track)
        needle = q.strip()
        if needle:
            # search_index понижен и транслитерирован в Питоне — основной путь.
            # ⚠️ SQLite lower() не берёт кириллицу, поэтому запасные условия —
            # по самим полям как есть: у части треков индекса нет (старые записи).
            normalized = normalize_search_query(needle)
            conditions = []
            # ⚠️ Пустой образец даёт LIKE '%%' — он подходит ко ВСЕМУ каталогу.
            # Так «ъъъъ» возвращал 7589 треков вместо нуля (замер на проде 16.09).
            if normalized:
                conditions.append(Track.search_index.like(f"%{normalized}%"))
            # «кизару» должно находить «kizaru»: индекс хранит и транслит,
            # но сам запрос не транслитерируется — как в поиске бота
            latin = to_latin(normalized)
            if latin and latin != normalized:
                conditions.append(Track.search_index.like(f"%{latin}%"))
            # Запасной путь для строк без индекса: сравниваем как есть и с
            # заглавной первой буквы — SQLite сам кириллицу не понижает
            for variant in {needle, needle.lower(), needle.capitalize(), needle.title()}:
                conditions.append(Track.artist.like(f"%{variant}%"))
                conditions.append(Track.title.like(f"%{variant}%"))
            query = query.where(or_(*conditions))
        total = await session.scalar(select(func.count()).select_from(query.subquery())) or 0
        rows = (await session.scalars(query.order_by(Track.id.desc()).limit(limit).offset(offset))).all()
        listens = dict(
            (
                await session.execute(
                    select(TrackEvent.track_id, func.count())
                    .where(TrackEvent.event == "listen", TrackEvent.track_id.in_([t.id for t in rows] or [0]))
                    .group_by(TrackEvent.track_id)
                )
            ).all()
        )
        return {
            "total": total,
            "items": [
                {
                    "id": t.id,
                    "artist": t.artist,
                    "title": t.title,
                    "duration": t.duration,
                    "mood": t.mood,
                    "album": t.album,
                    "playable": bool(t.tg_file_id),
                    "listens": listens.get(t.id, 0),
                }
                for t in rows
            ],
        }

    @app.get("/api/money")
    async def money(
        limit: int = Query(default=50, ge=1, le=200),
        session: AsyncSession = Depends(get_session),
        _: None = Depends(check_token),
    ) -> dict:
        payments = (
            await session.execute(
                select(Payment, User.telegram_id, User.first_name)
                .join(User, User.id == Payment.user_id, isouter=True)
                .order_by(Payment.created_at.desc())
                .limit(limit)
            )
        ).all()
        donations = (
            await session.execute(
                select(Donation, User.telegram_id, User.first_name)
                .join(User, User.id == Donation.user_id, isouter=True)
                .order_by(Donation.created_at.desc())
                .limit(limit)
            )
        ).all()
        return {
            "payments": [
                {
                    "id": p.id,
                    "created_at": p.created_at.isoformat() if p.created_at else None,
                    "rub": p.amount_rub,
                    "stars": p.amount_stars,
                    "source": p.source,
                    "months": getattr(p, "months", None),
                    "user": {"telegram_id": tid, "name": name},
                }
                for p, tid, name in payments
            ],
            "donations": [
                {
                    "id": d.id,
                    "created_at": d.created_at.isoformat() if d.created_at else None,
                    "rub": d.amount_rub,
                    "refunded": d.refunded_at is not None,
                    "user": {"telegram_id": tid, "name": name},
                }
                for d, tid, name in donations
            ],
        }

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(UI_DIR / "index.html")

    if UI_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=UI_DIR), name="static")
    return app


app = create_app()

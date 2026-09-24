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

import logging

from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import Body, Cookie, Depends, FastAPI, Header, HTTPException, Query, Response, status
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
from app.webadmin import auth

logger = logging.getLogger(__name__)

UI_DIR = Path(__file__).resolve().parents[2] / "webadmin"


async def get_session() -> AsyncSession:
    async with session_factory() as session:
        yield session


async def check_token(x_admin_token: str | None = Header(default=None)) -> None:
    """Старый рубеж по заголовку. Оставлен для скриптов и на случай, когда
    пароль ещё не заведён: тогда админка работает как раньше, по SSH-туннелю."""
    expected = getattr(settings, "webadmin_token", "") or ""
    if expected and x_admin_token != expected:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный токен админки")


async def guard(
    x_admin_token: str | None = Header(default=None),
    admin_session: str | None = Cookie(default=None),
) -> None:
    """Пропуск к данным: пароль + код в Telegram, если пароль настроен.

    Пароль не задан → остаётся прежний порядок (SSH-туннель плюс заголовок).
    Так обновление не запирает владельца снаружи собственной админки до того,
    как он успеет прописать пароль.
    """
    await check_token(x_admin_token)
    if auth.password_configured():
        await auth.require_session(admin_session)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def create_app() -> FastAPI:
    app = FastAPI(title="Infinity Music — админка", docs_url=None, redoc_url=None)

    @app.get("/api/overview", dependencies=[Depends(guard)])
    async def overview(
        days: int = Query(default=30, ge=1, le=365),
        session: AsyncSession = Depends(get_session),
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

    @app.get("/api/users", dependencies=[Depends(guard)])
    async def users(
        q: str = Query(default=""),
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
        session: AsyncSession = Depends(get_session),
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

    @app.get("/api/tracks", dependencies=[Depends(guard)])
    async def tracks(
        q: str = Query(default=""),
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
        session: AsyncSession = Depends(get_session),
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

    @app.get("/api/money", dependencies=[Depends(guard)])
    async def money(
        limit: int = Query(default=50, ge=1, le=200),
        session: AsyncSession = Depends(get_session),
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

    # ---------- вход ----------

    @app.get("/api/session")
    async def session_state(admin_session: str | None = Cookie(default=None)) -> dict:
        """Состояние входа для страницы: нужен ли пароль и есть ли живая сессия."""
        return {
            "password_required": auth.password_configured(),
            "authorized": not auth.password_configured() or auth.valid_session(admin_session),
            "code_pending": auth.challenge_pending(),
        }

    @app.post("/api/login")
    async def login(password: str = Body(embed=True)) -> dict:
        """Шаг 1: пароль. Верный — шлём одноразовый код в Telegram владельцу.

        ⚠️ Ответ одинаков по времени и по форме для верного и неверного пароля
        ровно настолько, насколько это возможно без усложнения: разницу даёт
        только текст. Перебор всё равно упирается в общий счётчик попыток.
        """
        auth.raise_if_locked()
        if not auth.password_configured():
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Пароль админки не настроен")
        if not auth.verify_password(password):
            auth.note_failure()
            raise auth.AuthError("Неверный пароль")
        code = auth.start_challenge()
        chat_id = settings.webadmin_code_chat_id
        if not chat_id:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Некуда слать код: пуст ADMIN_IDS")
        try:
            from app.services.bot_api import BotApi

            async with BotApi() as bot:
                await bot.send_message(
                    chat_id,
                    f"Код входа в админку: {code}\n"
                    f"Действует 5 минут. "
                    "Если вы не открывали админку — кто-то знает пароль, смените его.",
                )
        except Exception as exc:  # noqa: BLE001 — Telegram лёг: честно говорим, а не молчим
            logger.warning("Код админки не ушёл: %s", exc)
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY, "Не удалось отправить код в Telegram"
            ) from None
        return {"stage": "code"}

    @app.post("/api/login/code")
    async def login_code(response: Response, code: str = Body(embed=True)) -> dict:
        auth.raise_if_locked()
        if not auth.check_challenge(code):
            auth.note_failure()
            raise auth.AuthError("Неверный код")
        auth.reset_failures()
        response.set_cookie(
            auth.SESSION_COOKIE,
            auth.issue_session(),
            max_age=auth.SESSION_TTL_SECONDS,
            httponly=True,
            samesite="strict",
        )
        return {"authorized": True}

    @app.post("/api/logout")
    async def logout(response: Response) -> dict:
        response.delete_cookie(auth.SESSION_COOKIE)
        return {"authorized": False}

    # ---------- действия ----------

    @app.post("/api/users/{telegram_id}/premium", dependencies=[Depends(guard)])
    async def grant_premium(
        telegram_id: int,
        days: int = Body(embed=True, default=30),
        session: AsyncSession = Depends(get_session),
    ) -> dict:
        """Выдать или снять Premium руками.

        Отрицательные дни допустимы намеренно: так подписка укорачивается, а
        `days=0` снимает её совсем. Иначе пришлось бы лезть в базу руками —
        именно этого владелец и просил избежать.
        """
        if not -3650 <= days <= 3650:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Слишком большой срок")
        user = await session.scalar(select(User).where(User.telegram_id == telegram_id))
        if user is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Пользователь не найден")
        now = _utcnow()
        if days == 0:
            user.premium_until = None
            user.premium = False
        else:
            base = user.premium_until if user.premium_until and user.premium_until > now else now
            user.premium_until = base + timedelta(days=days)
            user.premium = user.premium_until > now
        await session.commit()
        logger.info("Админка: premium user=%s days=%s", telegram_id, days)
        return {
            "telegram_id": telegram_id,
            "premium_until": user.premium_until.isoformat() if user.premium_until else None,
        }

    @app.post("/api/broadcast", dependencies=[Depends(guard)])
    async def broadcast(
        text: str = Body(embed=True),
        confirm: bool = Body(embed=True, default=False),
        session: AsyncSession = Depends(get_session),
    ) -> dict:
        """Рассылка всем неотписавшимся. Без confirm возвращает только охват.

        ⚠️ Два шага намеренно: отправить письмо тысячам людей нельзя случайным
        кликом. Первый запрос говорит, скольким уйдёт, второй — отправляет.
        """
        text = (text or "").strip()
        if not text:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Пустой текст")
        reach = await session.scalar(
            select(func.count()).select_from(User).where(User.bot_blocked.is_(False))
        )
        if not confirm:
            return {"reach": reach or 0, "sent": False}
        try:
            from app.tasks.queue_client import enqueue

            enqueue("broadcast.send", text=text, photo_file_id=None)
        except Exception as exc:  # noqa: BLE001 — брокер лёг
            logger.warning("Рассылка из админки не поставилась: %s", exc)
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, "Очередь недоступна — рассылка не запущена"
            ) from None
        return {"reach": reach or 0, "sent": True}

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(UI_DIR / "index.html")

    if UI_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=UI_DIR), name="static")
    return app


app = create_app()

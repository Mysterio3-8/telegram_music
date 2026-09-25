"""Воронка «пришёл → нашёл трек → вернулся → заплатил» для админки (25.09).

Владелец: «прям хочется видеть… приходят ли люди, остаются ли они, это самое
главное… люди не приходят — узнавать почему». Шаги знакомства (/start, гейт,
кабинет, вход в Mini App, пэйвол) уже пишутся в `funnel_events`, но их видно
только из командной строки, и в них нет главного — нашёл ли человек музыку и
вернулся ли. Эти шаги берём из того, что и так лежит в базе: поисковые
запросы, события прослушивания, платежи.

Когорта — люди, пришедшие за окно (шаг «start»). Иначе давние пользователи,
впервые открывшие Mini App, раздували бы нижние ступени, и воронка врала бы.

⚠️ Только числа по людям — ни одного имени. Владелец сам поставил условие:
«каждого пользователя конкретно — конфиденциальность нельзя раскрывать».
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import FunnelEvent, Payment, SearchQuery, TrackEvent, User


@dataclass(frozen=True)
class FunnelStep:
    key: str
    label: str
    people: int


# Порядок — порядок пути человека. Подписи — для владельца, а не для инженера.
_LABELS: dict[str, str] = {
    "start": "Пришли (/start)",
    "gate_passed": "Прошли подписку на каналы",
    "searched": "Искали трек",
    "got_track": "Получили хотя бы один трек",
    "returned": "Вернулись на следующий день или позже",
    "miniapp_login": "Открыли плеер (Mini App)",
    "paywall_hit": "Упёрлись в пэйвол плеера",
    "paid": "Заплатили",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def build_funnel(session: AsyncSession, days: int = 30) -> list[FunnelStep]:
    since = _utcnow() - timedelta(days=days)
    cohort_ids = list(
        (
            await session.scalars(
                select(FunnelEvent.user_id)
                .where(FunnelEvent.step == "start", FunnelEvent.created_at >= since)
                .distinct()
            )
        ).all()
    )
    if not cohort_ids:
        return [FunnelStep(key, label, 0) for key, label in _LABELS.items()]

    in_cohort = User.id.in_(cohort_ids)

    async def count(condition) -> int:
        return await session.scalar(select(func.count()).select_from(User).where(in_cohort, condition)) or 0

    logged = dict(
        (
            await session.execute(
                select(FunnelEvent.step, func.count(func.distinct(FunnelEvent.user_id)))
                .where(FunnelEvent.user_id.in_(cohort_ids))
                .group_by(FunnelEvent.step)
            )
        ).all()
    )

    searched = await count(exists().where(SearchQuery.user_id == User.id))
    got_track = await count(exists().where(TrackEvent.user_id == User.id))
    # «Вернулся» — любое действие позже первых суток после прихода. Событие
    # прослушивания или поиск, а не просто /start: открыть бота ещё не значит
    # вернуться к музыке.
    # ⚠️ Сравнение в Питоне, а не в SQL: `created_at + timedelta` SQLite
    # превращает в сложение чисел, и первая версия засчитывала возврат тому,
    # кто слушал в тот же день (поймано тестом).
    joined = dict((await session.execute(select(User.id, User.created_at).where(in_cohort))).all())
    last_seen: dict[int, datetime] = {}
    for model in (TrackEvent, SearchQuery):
        rows = await session.execute(
            select(model.user_id, func.max(model.created_at))
            .where(model.user_id.in_(cohort_ids))
            .group_by(model.user_id)
        )
        for user_id, moment in rows.all():
            if moment and (user_id not in last_seen or moment > last_seen[user_id]):
                last_seen[user_id] = moment
    returned = sum(
        1
        for user_id, moment in last_seen.items()
        if joined.get(user_id) and moment >= joined[user_id] + timedelta(days=1)
    )
    paid = await count(exists().where(Payment.user_id == User.id))

    values = {
        "start": len(cohort_ids),
        "gate_passed": logged.get("gate_passed", 0),
        "searched": searched,
        "got_track": got_track,
        "returned": returned,
        "miniapp_login": logged.get("miniapp_login", 0),
        "paywall_hit": logged.get("paywall_hit", 0),
        "paid": paid,
    }
    return [FunnelStep(key, label, values[key]) for key, label in _LABELS.items()]

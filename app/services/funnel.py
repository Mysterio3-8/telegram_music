"""Шаги воронки новичка (15.09).

Замер прода 15.09: с 15.08 пришли 32 человека, гейт подписки прошли 26, а хоть
что-то сделали только 14 — 46% подписавшихся уходят из кабинета, не отправив даже
названия песни. Куда они нажимают, было не видно: открывают платный Mini App,
листают меню или просто закрывают чат.

Пишем ПЕРВОЕ прохождение каждого шага, одной строкой на пользователя и шаг —
таблица остаётся крошечной, а отчёт `python -m app.cli.funnel` считает людей.

⚠️ Аналитика не имеет права ломать сценарий: любая ошибка записи логируется и
глотается. Вызывать там, где у сессии нет незакоммиченных изменений вызывающего,
— при сбое делается rollback.
"""
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import FunnelEvent

logger = logging.getLogger(__name__)

# Порядок — порядок воронки; отчёт выводит шаги в нём.
STEPS: tuple[str, ...] = (
    "start",          # первый /start (новый пользователь)
    "lang_chosen",    # выбрал язык на первом входе
    "gate_shown",     # увидел гейт обязательной подписки
    "gate_passed",    # подписка подтверждена (сразу или кнопкой)
    "cabinet_shown",  # увидел кабинет с подсказкой «отправьте название песни»
    "miniapp_login",  # открыл Mini App (вход по initData)
    "paywall_hit",    # в Mini App упёрся в пэйвол (402)
)

# Уже записанное в этом процессе — чтобы пэйвол на каждом запросе не ходил в базу.
_SEEN_MAX = 50_000
_seen: set[tuple[int, str]] = set()


def forget_seen_steps() -> None:
    _seen.clear()


async def record_step(session: AsyncSession, user_id: int, step: str) -> None:
    if step not in STEPS:
        raise ValueError(f"неизвестный шаг воронки: {step}")
    key = (user_id, step)
    if key in _seen:
        return
    try:
        exists = await session.scalar(
            select(FunnelEvent.id)
            .where(FunnelEvent.user_id == user_id, FunnelEvent.step == step)
            .limit(1)
        )
        if exists is None:
            session.add(FunnelEvent(user_id=user_id, step=step))
            await session.commit()
    except Exception:  # noqa: BLE001 — аналитика не ломает сценарий
        logger.warning("Воронка: не записан шаг %s user=%s", step, user_id, exc_info=True)
        await session.rollback()
        return
    if len(_seen) >= _SEEN_MAX:
        _seen.clear()
    _seen.add(key)

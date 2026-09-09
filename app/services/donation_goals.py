"""Цели сбора: создание, прогресс, рейтинг по цели, текст поста.

⚠️ Прогресс нигде не хранится числом — он всегда считается суммой донатов с
этим `goal_id`. Хранимый счётчик был бы второй правдой о деньгах и разошёлся бы
с первой на первом же возврате: банк плательщика вернул деньги, `refunded_at`
проставился, а счётчик остался бы завышенным, и никто бы этого не заметил.

Модуль намеренно не знает про aiogram (инвариант проекта: services/ — чистая
логика). Публикация и правка поста в канале — в [app/services/goal_post.py],
там же, где живёт единственная причина трогать Bot.
"""
import logging
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Donation, DonationGoal, User

logger = logging.getLogger(__name__)

# Сколько последних донатов показываем в посте и на экране цели.
RECENT_LIMIT = 5
# Сколько человек в рейтинге по цели.
GOAL_TOP_LIMIT = 10
# Длина полосы прогресса в символах. 12 подобрано под ширину экрана телефона:
# длиннее — и полоса переносится на вторую строку, ломая вид поста.
BAR_WIDTH = 12
BAR_FULL = "█"
BAR_EMPTY = "░"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def active_goal(session: AsyncSession) -> DonationGoal | None:
    """Текущая цель или None, если сбора сейчас нет."""
    result = await session.execute(
        select(DonationGoal).where(DonationGoal.is_active.is_(True))
    )
    return result.scalar_one_or_none()


async def get_goal(session: AsyncSession, goal_id: int) -> DonationGoal | None:
    return await session.get(DonationGoal, goal_id)


async def create_goal(
    session: AsyncSession,
    *,
    title: str,
    target_rub: int,
    description: str | None = None,
    image_file_id: str | None = None,
    deadline: datetime | None = None,
) -> DonationGoal | None:
    """Завести цель. None — активная уже есть (одновременно живёт только одна).

    Проверку дублирует уникальный индекс в базе: между этим SELECT и INSERT
    может влезть второй админ, и тогда правило должна отстоять база, а не мы.
    """
    if await active_goal(session) is not None:
        return None
    goal = DonationGoal(
        title=title.strip(),
        description=(description or "").strip() or None,
        target_rub=target_rub,
        image_file_id=image_file_id,
        deadline=deadline,
        is_active=True,
    )
    session.add(goal)
    await session.commit()
    await session.refresh(goal)
    logger.info("Заведена цель #%s «%s» на %s ₽", goal.id, goal.title, goal.target_rub)
    return goal


async def close_goal(session: AsyncSession, goal: DonationGoal) -> None:
    """Закрыть цель. Донаты за ней остаются — это история, а не мусор.

    `is_active` уходит в NULL, а не в False: именно так уникальный индекс
    пропускает следующую активную цель (см. модель).
    """
    goal.is_active = None
    goal.closed_at = _utcnow()
    await session.commit()
    logger.info("Цель #%s «%s» закрыта", goal.id, goal.title)


async def goal_progress(session: AsyncSession, goal_id: int) -> int:
    """Сколько собрано по цели. Возвращённые донаты не в счёт."""
    result = await session.execute(
        select(func.coalesce(func.sum(Donation.amount_rub), 0)).where(
            Donation.goal_id == goal_id,
            Donation.refunded_at.is_(None),
        )
    )
    return int(result.scalar_one())


async def mark_reached(session: AsyncSession, goal: DonationGoal, raised: int) -> bool:
    """Отметить достижение цели. True — отметили именно сейчас (первый раз).

    Возврат True — сигнал «пора сообщить владельцу». Отметка ставится один раз:
    иначе каждый следующий донат сверх цели слал бы владельцу ещё одно
    поздравление.
    """
    if goal.reached_at is not None or raised < goal.target_rub:
        return False
    goal.reached_at = _utcnow()
    await session.commit()
    logger.info("Цель #%s достигнута: %s из %s ₽", goal.id, raised, goal.target_rub)
    return True


async def recent_donations(
    session: AsyncSession, goal_id: int, limit: int = RECENT_LIMIT
) -> list[tuple[User, int, bool]]:
    """Последние донаты цели: (кто, сколько, аноним ли). Свежие первыми."""
    result = await session.execute(
        select(User, Donation.amount_rub, Donation.is_anonymous)
        .join(Donation, Donation.user_id == User.id)
        .where(Donation.goal_id == goal_id, Donation.refunded_at.is_(None))
        .order_by(Donation.created_at.desc(), Donation.id.desc())
        .limit(limit)
    )
    return [(user, int(amount), bool(anon)) for user, amount, anon in result.all()]


async def goal_top(
    session: AsyncSession, goal_id: int, limit: int = GOAL_TOP_LIMIT
) -> list[tuple[User, int]]:
    """Рейтинг вкладчиков ИМЕННО этой цели.

    ⚠️ Анонимы отсеиваются здесь, в запросе, а не при отрисовке: иначе их место
    в списке всё равно было бы видно по разрыву в нумерации.
    """
    total = func.sum(Donation.amount_rub).label("total")
    result = await session.execute(
        select(User, total)
        .join(Donation, Donation.user_id == User.id)
        .where(
            Donation.goal_id == goal_id,
            Donation.refunded_at.is_(None),
            Donation.is_anonymous.is_(False),
        )
        .group_by(User.id)
        .order_by(total.desc(), User.id)
        .limit(limit)
    )
    return [(user, int(amount)) for user, amount in result.all()]


def progress_percent(raised: int, target: int) -> int:
    """Процент сбора, целым числом. Больше 100 не срезается — сбор бывает сверх цели."""
    if target <= 0:
        return 0
    return int(raised * 100 / target)


def progress_bar(raised: int, target: int, width: int = BAR_WIDTH) -> str:
    """Полоса прогресса символами.

    ⚠️ Полоса обрезается по ширине, а процент — нет: при сборе 140% полоса
    честно закрашена целиком, а «140%» стоит рядом числом. Рисовать полосу
    длиннее ширины нельзя — она переносится и разваливает пост.
    """
    if target <= 0:
        return BAR_EMPTY * width
    filled = min(width, max(0, round(raised * width / target)))
    # Один закрашенный сегмент при любом ненулевом сборе: пустая полоса рядом с
    # «собрано 300 ₽» читается как «не собрано ничего».
    if raised > 0 and filled == 0:
        filled = 1
    return BAR_FULL * filled + BAR_EMPTY * (width - filled)


def days_left(goal: DonationGoal, now: datetime | None = None) -> int | None:
    """Дней до срока. None — срока нет. Отрицательное — срок вышел."""
    if goal.deadline is None:
        return None
    current = now or _utcnow()
    return (goal.deadline.date() - current.date()).days

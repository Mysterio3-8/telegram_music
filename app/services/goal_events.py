"""Что происходит после зачтённого доната: пост и сигнал владельцу.

Отдельно от [donation_goals.py](app/services/donation_goals.py) намеренно: там
чистые запросы, которые легко проверять тестом, здесь — обращения наружу, к
Telegram. Смешай их, и тест на прогресс цели начал бы стучаться в сеть.

⚠️ Ни одна ошибка отсюда не должна долететь до вызывающего кода. Зовут нас из
обработчика вебхука кассы: деньги уже приняты, и упасть здесь значит ответить
кассе ошибкой и получить повтор уведомления — по кругу, пока вебхук не отключат.
"""
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import Donation

logger = logging.getLogger(__name__)


async def after_donation(session: AsyncSession, donation: Donation) -> None:
    """Перерисовать пост цели и, если цель только что взята, сказать владельцу."""
    if donation.goal_id is None:
        return  # донат вне сбора — перерисовывать нечего

    from app.services import donation_goals as goals
    from app.services import goal_post
    from app.services.telegram_send import send_message

    try:
        goal = await goals.get_goal(session, donation.goal_id)
        if goal is None:
            return

        raised = await goals.goal_progress(session, goal.id)
        just_reached = await goals.mark_reached(session, goal, raised)

        # Пост правится ПОСЛЕ отметки о достижении: иначе в канале ещё висел бы
        # сбор без строчки «цель собрана», хотя она уже собрана.
        await goal_post.refresh(session, goal)

        if just_reached:
            owner = settings.health_alert_id
            if owner:
                await send_message(
                    owner,
                    f"🎯 Цель «{goal.title}» собрана: "
                    f"{raised} ₽ из {goal.target_rub} ₽.\n\n"
                    "Сбор продолжается — закрыть цель и завести следующую "
                    "можно в /admin → Цели сбора.",
                )
    except Exception:  # noqa: BLE001 — см. docstring модуля
        logger.exception("После доната %s не удалось обновить цель", donation.payment_id)

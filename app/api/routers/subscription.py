"""Статус обязательной подписки для Mini App (блок B).

Mini App гейтит доступ так же, как бот: не подписан на обязательные каналы —
показываем экран-гейт. Premium и админы (при bypass) от гейта освобождены.
Проверка идёт тем же getChatMember с TTL-кэшем, что и в боте.
"""
import time

from aiogram import Bot
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.api.schemas import SubChannelOut, SubscriptionStatusOut
from app.config import settings
from app.db.models import User
from app.services.premium import is_premium_active
from app.services.required_channels import (
    channel_url,
    get_required_channels,
    register_channel_click,
)
from app.services.subscription import is_channel_subscribed
from app.services.users import is_admin

router = APIRouter(tags=["subscription"])

# Последний засчитанный клик (user_id, channel_id) → monotonic. В памяти, как и
# лимитер: uvicorn один процесс, а запись на диск при флуде уже роняла прод.
_CLICK_WINDOW = 3600.0
_CLICKS_MAX = 10_000
_recent_clicks: dict[tuple[int, int], float] = {}


@router.get("/subscription/status", response_model=SubscriptionStatusOut)
async def subscription_status(
    force: bool = Query(False),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> SubscriptionStatusOut:
    channels = await get_required_channels(session)
    bypass = settings.admin_bypass_subscription and is_admin(user.telegram_id)
    if not channels or bypass or is_premium_active(user):
        return SubscriptionStatusOut(required=False, subscribed=True, channels=[])

    bot = Bot(token=settings.bot_token)
    try:
        subscribed = True
        out: list[SubChannelOut] = []
        for row in channels:
            is_sub = True  # запуск чужого бота (kind=bot) проверить нельзя — не блокирует
            if row.kind == "channel":
                is_sub = await is_channel_subscribed(
                    session, bot, user.id, user.telegram_id, row.channel, force
                )
                if not is_sub:
                    subscribed = False
            out.append(
                SubChannelOut(
                    id=row.id,
                    label=row.label,
                    url=channel_url(row),
                    kind=row.kind,
                    subscribed=is_sub,
                )
            )
    finally:
        await bot.session.close()

    return SubscriptionStatusOut(required=True, subscribed=subscribed, channels=out)


@router.post("/subscription/click/{channel_id}", status_code=204)
async def channel_click(
    channel_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    """Клик по кнопке канала в гейте — воронка для продажи рекламы."""
    # Один человек — один клик по каналу в час. Иначе цикл запросов накручивал
    # счётчик, по которому продаётся реклама (замер: +30 за 30 запросов).
    now = time.monotonic()
    if len(_recent_clicks) > _CLICKS_MAX:
        for key in [k for k, at in _recent_clicks.items() if now - at > _CLICK_WINDOW]:
            _recent_clicks.pop(key, None)
    key = (user.id, channel_id)
    seen = _recent_clicks.get(key)
    if seen is not None and now - seen < _CLICK_WINDOW:
        return
    _recent_clicks[key] = now
    await register_channel_click(session, channel_id)

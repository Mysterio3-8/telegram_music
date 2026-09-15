"""События аналитики из Mini App (15.09): дослушал/пропустил, экраны, пэйвол, «поделиться».

Открыт без Premium (только вход): пэйвол и первые экраны видят как раз бесплатные.
Пачка до 50 событий — клиент копит их и шлёт раз в несколько секунд, а не
запросом на каждое. Имена — только клиентские из белого списка: «listen» и
«download» пишет сервер сам, подделать их из браузера нельзя.
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.api.schemas import ClientEventsIn
from app.db.models import User
from app.services.analytics import build_event

router = APIRouter(tags=["analytics"])

CLIENT_EVENTS = frozenset(
    {"app_open", "play_complete", "play_skip", "screen_view", "share_click", "paywall_view"}
)


@router.post("/analytics/events", status_code=status.HTTP_204_NO_CONTENT)
async def collect_events(
    payload: ClientEventsIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    accepted = [
        build_event(
            item.name,
            source="miniapp",
            user_id=user.id,
            track_id=item.track_id if item.track_id and item.track_id > 0 else None,
            props=item.props,
        )
        for item in payload.events
        if item.name in CLIENT_EVENTS
    ]
    if accepted:
        session.add_all(accepted)
        await session.commit()

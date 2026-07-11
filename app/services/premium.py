from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import PremiumSubscription, User
from app.services.uploads import count_user_uploads
from app.services.users import count_playlists


def _utcnow() -> datetime:
    # Наивный UTC — SQLite хранит datetime без таймзоны, сравнения не должны падать на mix naive/aware
    return datetime.now(timezone.utc).replace(tzinfo=None)


def is_premium_active(user: User) -> bool:
    return bool(user.premium and user.premium_until and user.premium_until > _utcnow())


async def refresh_premium_status(session: AsyncSession, user: User) -> User:
    """Снимает флаг premium, если срок истёк. Пишет в БД только при изменении."""
    if user.premium and not is_premium_active(user):
        user.premium = False
        await session.commit()
    return user


async def activate_premium(
    session: AsyncSession, user_id: int, payment_type: str, payment_id: str
) -> User:
    now = _utcnow()
    user = await session.get(User, user_id)
    # Продление действующей подписки прибавляется к остатку, а не обнуляет его
    base = user.premium_until if is_premium_active(user) else now
    end = base + timedelta(days=settings.premium_duration_days)

    user.premium = True
    user.premium_until = end

    subscription = await session.get(PremiumSubscription, user_id)
    if subscription is None:
        subscription = PremiumSubscription(user_id=user_id, start_date=now)
        session.add(subscription)
    subscription.status = "active"
    subscription.type = payment_type
    subscription.end_date = end
    subscription.payment_id = payment_id
    await session.commit()
    return user


async def can_create_playlist(session: AsyncSession, user: User) -> bool:
    if is_premium_active(user):
        return True
    return await count_playlists(session, user.id) < settings.free_playlist_limit


async def can_upload(session: AsyncSession, user: User) -> bool:
    if is_premium_active(user):
        return True
    return await count_user_uploads(session, user.id) < settings.free_upload_limit

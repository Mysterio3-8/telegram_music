from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import PremiumSubscription, User
from app.services.uploads import count_user_uploads
from app.services.users import count_playlists


# Тарифы Premium (ТЗ §24): месяцы → множитель цены.
PREMIUM_PLAN_MONTHS: tuple[int, ...] = (1, 3, 6, 12)
# «Навсегда»: ~100 лет по механике продления = вечная подписка. Цена — фиксированная.
FOREVER_MONTHS = 1200

# Скидка за длинный срок, % (решение владельца: «чем больше месяцев — чуть-чуть
# дешевле»). Небольшая сознательно: подписка и так стоит как две поездки в метро,
# а глубокая скидка на годовом тарифе съедает выручку, которая нужна на сервер.
PREMIUM_PLAN_DISCOUNTS: dict[int, int] = {1: 0, 3: 10, 6: 15, 12: 20}


def is_forever(months: int) -> bool:
    return months >= FOREVER_MONTHS


def plan_valid(months: int) -> bool:
    return months in PREMIUM_PLAN_MONTHS or is_forever(months)


def plan_discount_pct(months: int) -> int:
    """Скидка тарифа за срок. «Навсегда» не скидываем — цена и так фиксированная."""
    return 0 if is_forever(months) else PREMIUM_PLAN_DISCOUNTS.get(months, 0)


def plan_price_rub(months: int, discount_pct: int = 0) -> int:
    """Цена тарифа в рублях: скидка за срок плюс персональная (реферальная).
    Тариф «навсегда» — фиксированная цена без скидок."""
    if is_forever(months):
        return settings.premium_forever_price_rub
    base = settings.premium_price_rub * months
    total_discount = min(90, plan_discount_pct(months) + discount_pct)
    return base * (100 - total_discount) // 100 if total_discount else base


def plan_price_stars(months: int) -> int:
    """Цена тарифа в Telegram Stars.

    Считается по той же лестнице скидок, что и рубли, — иначе годовой тариф был
    бы выгоден в одной валюте и невыгоден в другой, и человек ловил бы нас на
    несоответствии. Персональной (реферальной) скидки здесь нет: Stars уходят
    Telegram напрямую, и произвольную цену за них не выставить.

    ⚠️ Курс Stars к рублю плавающий, поэтому суммы намеренно НЕ связаны
    формулой с `premium_price_rub`: цену в звёздах владелец задаёт отдельно
    (`PREMIUM_PRICE_STARS`), и она не должна прыгать вслед за курсом.
    """
    if is_forever(months):
        return settings.premium_forever_price_stars
    base = settings.premium_price_stars * months
    discount = plan_discount_pct(months)
    return max(1, base * (100 - discount) // 100) if discount else base


def _utcnow() -> datetime:
    # Наивный UTC — SQLite хранит datetime без таймзоны, сравнения не должны падать на mix naive/aware
    return datetime.now(timezone.utc).replace(tzinfo=None)


def is_premium_active(user: User) -> bool:
    """Админам Premium всегда доступен: иначе владелец с истёкшей подпиской
    упрётся в пэйвол приложения и не сможет проверить собственный сервис."""
    if user.telegram_id in settings.admin_id_set:
        return True
    return bool(user.premium and user.premium_until and user.premium_until > _utcnow())


async def refresh_premium_status(session: AsyncSession, user: User) -> User:
    """Снимает флаг premium, если срок истёк. Пишет в БД только при изменении."""
    if user.premium and not is_premium_active(user):
        user.premium = False
        await session.commit()
    return user


async def activate_premium(
    session: AsyncSession, user_id: int, payment_type: str, payment_id: str, months: int = 1
) -> User:
    now = _utcnow()
    user = await session.get(User, user_id)
    # Продление действующей подписки прибавляется к остатку, а не обнуляет его
    base = user.premium_until if is_premium_active(user) else now
    end = base + timedelta(days=settings.premium_duration_days * max(1, months))

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
    if settings.free_upload_limit <= 0:  # лимит на количество загрузок снят
        return True
    return await count_user_uploads(session, user.id) < settings.free_upload_limit

"""Донаты: приём добровольной поддержки и рейтинг спонсоров.

⚠️ Донат — ДАРЕНИЕ, а не покупка. За него принципиально не выдаётся ничего:
ни Premium, ни бонусов, ни снятия рекламы. Это не жадность, а условие, на
котором платёж остаётся дарением: появись встречная услуга — это уже
реализация, с кассовым чеком и другой отчётностью. Поэтому здесь нет и не
должно появиться ни одного вызова activate_premium.
"""
import logging
import math
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Donation, User

logger = logging.getLogger(__name__)

# Кнопки быстрых сумм (решение владельца).
DONATE_PRESETS = (49, 149, 249, 499)

# Границы «своей суммы». Нижняя отсекает платежи, которые целиком съедает
# комиссия кассы; верхняя ловит опечатку в лишний ноль — такой платёж почти
# всегда заканчивается возвратом и разбирательством.
MIN_AMOUNT_RUB = 10
MAX_AMOUNT_RUB = 100_000

# Сколько человек показываем в рейтинге.
TOP_LIMIT = 25


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def parse_amount(raw: str) -> int | None:
    """Своя сумма из текста. None — не число или вне границ.

    Только целые рубли и только цифры: `float()` здесь был бы дырой — он
    принимает "1e5", "  49.9 ", "inf" и "nan", а inf/nan потом уехали бы в
    платёж. Пробелы и разделители тысяч из «1 000» и «1_000» убираем, потому
    что люди их пишут, а вот копейки не поддерживаем сознательно — касса всё
    равно получает целое.
    """
    cleaned = raw.strip().replace(" ", "").replace(" ", "").replace("_", "")
    cleaned = cleaned.removesuffix("₽").removesuffix("руб").removesuffix("р").strip()
    # ⚠️ Только ASCII-цифры. `str.isdigit()` истинен и для «²», и для арабских
    # «٤٩», но `int("²")` падает с ValueError — то есть проверка пропускала бы
    # строку, на которой следующая же строка кода валится. Найдено тестом.
    if not (cleaned.isascii() and cleaned.isdigit()):
        return None
    amount = int(cleaned)
    if not (MIN_AMOUNT_RUB <= amount <= MAX_AMOUNT_RUB):
        return None
    return amount


def is_allowed_amount(amount: int) -> bool:
    """Сумма пришла из callback_data — проверяем её здесь, а не доверяем кнопке.

    callback_data подделывается кем угодно: Telegram отдаёт боту то, что прислал
    клиент. Без этой проверки можно было бы прислать don:pay:1 и попасть в
    рейтинг за рубль, а то и отрицательную сумму.
    """
    return amount in DONATE_PRESETS or MIN_AMOUNT_RUB <= amount <= MAX_AMOUNT_RUB


async def record_donation(
    session: AsyncSession,
    user_id: int,
    amount_rub: int,
    payment_id: str,
    *,
    provider: str = "yookassa",
    is_anonymous: bool = False,
    ton_nano: int | None = None,
    rub_per_ton: int | None = None,
    stars: int | None = None,
) -> Donation | None:
    """Записывает подтверждённый донат. None — такой платёж уже учтён.

    Идемпотентность по payment_id обязательна: ЮKassa повторяет уведомление,
    пока не получит 200, и повтор не должен удваивать вклад в рейтинге.

    ⚠️ Цель проставляется ЗДЕСЬ, на момент зачисления, а не при показе. Донат
    навсегда приписан к той цели, которая была активна в секунду оплаты: заведи
    владелец завтра новую — прогресс старой не должен ни вырасти, ни усохнуть.
    Донат вне сбора (целей нет вовсе) получает NULL и просто идёт в общий топ.
    """
    from app.services.donation_goals import active_goal

    existing = await session.scalar(select(Donation).where(Donation.payment_id == payment_id))
    if existing is not None:
        return None
    goal = await active_goal(session)
    donation = Donation(
        user_id=user_id,
        amount_rub=amount_rub,
        payment_id=payment_id,
        provider=provider,
        is_anonymous=is_anonymous,
        ton_nano=ton_nano,
        rub_per_ton=rub_per_ton,
        stars=stars,
        goal_id=goal.id if goal is not None else None,
    )
    session.add(donation)
    await session.flush()
    return donation


# --- Telegram Stars ----------------------------------------------------------

# Префикс payload счёта-доната в звёздах. Живёт здесь, а не в хендлере: по нему
# ДВА разных роутера (Premium и донаты) решают, чей это платёж, и расходиться в
# написании им нельзя — иначе донат уехал бы в выдачу Premium.
DONATE_STARS_PAYLOAD = "donate_stars"
# Потолок счёта в звёздах. Bot API не даёт выставить больше 10 000 ⭐ за раз,
# и счёт сверх этого Telegram просто отвергнет, не объяснив человеку почему.
MAX_STARS_PER_INVOICE = 10_000


def is_stars_configured() -> bool:
    """Принимаем ли донаты звёздами. Без курса — нет: не во что пересчитать."""
    from app.config import settings

    return settings.stars_rub_rate > 0


def _stars_exact(amount_rub: int) -> int:
    from app.config import settings

    rate = settings.stars_rub_rate
    if rate <= 0:
        raise ValueError("Курс звезды не задан (STARS_RUB_RATE)")
    # round(…, 6) до ceil обязателен: 49 / 0.7 в плавающей точке даёт
    # 70.00000000000001, и голый ceil запросил бы у человека 71 звезду вместо 70.
    return max(1, math.ceil(round(amount_rub / rate, 6)))


def can_pay_in_stars(amount_rub: int) -> bool:
    """Звёзды включены и сумма влезает в один счёт.

    🔴 Сумму сверх потолка НЕ обрезаем до 10 000 ⭐: тогда человек заплатил бы
    меньше, а в цель легла бы вся выбранная сумма. Такую сумму звёздами просто
    не предлагаем — рубли и TON для неё остаются.
    """
    return is_stars_configured() and _stars_exact(amount_rub) <= MAX_STARS_PER_INVOICE


def stars_for_rub(amount_rub: int) -> int:
    """Сколько звёзд попросить за сумму в рублях. Округление ВВЕРХ.

    Вверх, потому что иначе за «49 ₽» человек отдал бы звёзд на 48 ₽, и в цель
    легла бы сумма меньше той, что он выбрал на кнопке. Сумма сверх потолка
    счёта — ValueError: сперва спросить can_pay_in_stars.
    """
    stars = _stars_exact(amount_rub)
    if stars > MAX_STARS_PER_INVOICE:
        raise ValueError(f"{amount_rub} ₽ не влезает в один счёт звёздами")
    return stars


def rub_for_stars(stars: int) -> int:
    """Пришедшие звёзды → рубли в прогресс цели, целыми рублями вниз.

    Вниз по той же причине, что и у TON: округление вверх приписало бы рубль,
    которого никто не давал.
    """
    from app.config import settings

    # round(…, 6) до floor — та же грабля плавающей точки, что и в stars_for_rub,
    # только в обратную сторону: 70 * 0.7 = 48.99999999999999, и голый int()
    # записал бы в цель 48 ₽ за донат, который человек выбрал на кнопке «49 ₽».
    return math.floor(round(stars * settings.stars_rub_rate, 6))


def stars_payload(amount_rub: int, anonymous: bool) -> str:
    """payload счёта: «donate_stars:<анонимно 1|0>:<рубли>».

    Рубли едут в счёте, а не пересчитываются из звёзд при оплате: между счётом и
    оплатой владелец может сменить курс (или вовсе обнулить его, выключив звёзды),
    и тогда в цель легла бы не та сумма, что человек видел на кнопке. Подделать
    payload нельзя — счёт выставляет только сам бот.
    """
    return f"{DONATE_STARS_PAYLOAD}:{1 if anonymous else 0}:{amount_rub}"


def parse_stars_payload(payload: str | None) -> tuple[bool, int | None] | None:
    """payload → (анонимно, рубли). None — это не наш донатный счёт.

    Рубли None — в payload их нет или они вне границ; тогда сумму считают по
    звёздам. Так разбираются и счета, выставленные до появления суммы в payload.
    """
    parts = (payload or "").split(":")
    if parts[0] != DONATE_STARS_PAYLOAD:
        return None
    anonymous = len(parts) > 1 and parts[1] == "1"
    raw = parts[2] if len(parts) > 2 else ""
    amount = int(raw) if raw.isascii() and raw.isdigit() else None
    if amount is not None and not is_allowed_amount(amount):
        amount = None
    return anonymous, amount


async def mark_refunded(session: AsyncSession, payment_id: str) -> bool:
    """Деньги ушли обратно — донат выпадает из рейтинга. True, если нашли.

    Сами мы возвраты не делаем, но чарджбэк инициирует банк плательщика, и
    запретить его правилами нельзя. Без этой отметки человек, оспоривший платёж,
    навсегда остался бы в топе за чужой счёт.
    """
    donation = await session.scalar(select(Donation).where(Donation.payment_id == payment_id))
    if donation is None:
        return False
    if donation.refunded_at is None:
        donation.refunded_at = _utcnow()
        await session.flush()
        logger.info("Донат %s помечен возвращённым (user=%s)", payment_id, donation.user_id)
    return True


def display_name(user: User) -> str:
    """Как человек подписан в рейтинге.

    Юзернейм, если он есть. Иначе «Спонсор #id» — обезличенно, но стабильно:
    человек узнаёт себя по одному и тому же номеру между заходами.

    ⚠️ Имя из профиля (first_name) сюда сознательно НЕ идёт: его человек пишет
    себе сам, и в публичный список уехали бы и реклама, и чужие @ники, и мат.
    Юзернейм такого не позволяет — Telegram ограничивает его латиницей, цифрами
    и подчёркиванием.
    """
    if user.username:
        return f"@{user.username}"
    return f"Спонсор #{user.id}"


async def top_sponsors(session: AsyncSession, limit: int = TOP_LIMIT) -> list[tuple[User, int]]:
    """Топ спонсоров по сумме всех донатов. Нулевые и возвращённые не в счёт."""
    total = func.sum(Donation.amount_rub).label("total")
    rows = (
        await session.execute(
            select(User, total)
            .join(Donation, Donation.user_id == User.id)
            .where(Donation.refunded_at.is_(None))
            .group_by(User.id)
            # 0 ₽ не показываем (требование владельца). Появиться такая сумма
            # может только из возврата части денег, но проверить дёшево.
            .having(total > 0)
            .order_by(total.desc(), User.id)
            .limit(limit)
        )
    ).all()
    return [(row[0], int(row[1])) for row in rows]


async def user_total(session: AsyncSession, user_id: int) -> int:
    """Сколько человек задонатил всего (без возвращённого)."""
    total = await session.scalar(
        select(func.coalesce(func.sum(Donation.amount_rub), 0)).where(
            Donation.user_id == user_id, Donation.refunded_at.is_(None)
        )
    )
    return int(total or 0)


async def user_rank(session: AsyncSession, user_id: int) -> int | None:
    """Место человека в общем зачёте (1 — первое). None — донатов нет.

    Считаем по всем донатерам, а не только по видимой двадцатьпятке: человеку на
    30-м месте важно знать, что он тридцатый, а не «вас нет в списке».
    """
    mine = await user_total(session, user_id)
    if mine <= 0:
        return None
    total = func.sum(Donation.amount_rub).label("total")
    better = (
        select(func.count())
        .select_from(
            select(Donation.user_id, total)
            .where(Donation.refunded_at.is_(None))
            .group_by(Donation.user_id)
            .having(total > mine)
            .subquery()
        )
    )
    return int(await session.scalar(better) or 0) + 1


async def donations_summary(session: AsyncSession) -> tuple[int, int]:
    """Для админ-статистики: (сумма в рублях, число донатов) без возвращённых."""
    row = (
        await session.execute(
            select(
                func.coalesce(func.sum(Donation.amount_rub), 0),
                func.count(Donation.id),
            ).where(Donation.refunded_at.is_(None))
        )
    ).one()
    return int(row[0] or 0), int(row[1] or 0)

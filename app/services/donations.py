"""Донаты: приём добровольной поддержки и рейтинг спонсоров.

⚠️ Донат — ДАРЕНИЕ, а не покупка. За него принципиально не выдаётся ничего:
ни Premium, ни бонусов, ни снятия рекламы. Это не жадность, а условие, на
котором платёж остаётся дарением: появись встречная услуга — это уже
реализация, с кассовым чеком и другой отчётностью. Поэтому здесь нет и не
должно появиться ни одного вызова activate_premium.
"""
import logging
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
    session: AsyncSession, user_id: int, amount_rub: int, payment_id: str
) -> Donation | None:
    """Записывает подтверждённый донат. None — такой платёж уже учтён.

    Идемпотентность по payment_id обязательна: ЮKassa повторяет уведомление,
    пока не получит 200, и повтор не должен удваивать вклад в рейтинге.
    """
    existing = await session.scalar(select(Donation).where(Donation.payment_id == payment_id))
    if existing is not None:
        return None
    donation = Donation(user_id=user_id, amount_rub=amount_rub, payment_id=payment_id)
    session.add(donation)
    await session.flush()
    return donation


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

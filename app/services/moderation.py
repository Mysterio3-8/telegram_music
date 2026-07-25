"""Автомодерация загруженных пользователями треков (блок D).

Загрузка со стоп-словом (терроризм/экстремизм/насилие) не блокируется жёстко, а
уходит на ручное одобрение: трек создаётся со статусом pending и скрыт из поиска,
микса и алгоритма продвижения, пока админ не одобрит. Так «революционное» аудио
не выстрелит в топ автоматически. Автор может оспорить через поддержку (блок F).

Список намеренно узкий — ловим только явно опасные темы, а не мат/18+.
"""
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Track

STATUS_APPROVED = "approved"
STATUS_PENDING = "pending"
STATUS_REJECTED = "rejected"

# Стоп-слова (корни, регистр игнорируется). Ищем как отдельные слова, чтобы
# «террор» не ловил безобидные вхождения внутри других слов.
_STOP_WORDS = (
    r"террор\w*",
    r"terror\w*",
    r"теракт\w*",
    r"экстремизм\w*",
    r"extremis\w*",
    r"джихад\w*",
    r"jihad\w*",
    r"игил",
    r"isis",
    r"ваххаб\w*",
    r"нацизм\w*",
    r"na[sz]ism\w*",
    r"холокост\w*",
    r"насилие",
    r"убий\w*",
    r"суицид\w*",
    r"suicide\w*",
    r"расправ\w*",
)

_STOP_RE = re.compile(r"\b(?:" + "|".join(_STOP_WORDS) + r")\b", re.IGNORECASE)


def is_flagged(*parts: str) -> bool:
    """True — в тексте (название/исполнитель) есть стоп-слово → на модерацию."""
    text = " ".join(p for p in parts if p)
    return bool(_STOP_RE.search(text))


def initial_status(title: str, artist: str) -> str:
    """Статус для нового пользовательского трека: pending при стоп-слове, иначе approved."""
    return STATUS_PENDING if is_flagged(title, artist) else STATUS_APPROVED


async def pending_tracks(session: AsyncSession, limit: int = 20) -> list[Track]:
    stmt = (
        select(Track)
        .where(Track.moderation_status == STATUS_PENDING)
        .order_by(Track.created_at)
        .limit(limit)
    )
    return list((await session.scalars(stmt)).all())


async def count_pending(session: AsyncSession) -> int:
    from sqlalchemy import func

    return await session.scalar(
        select(func.count()).select_from(Track).where(Track.moderation_status == STATUS_PENDING)
    ) or 0


async def set_status(session: AsyncSession, track_id: int, status: str) -> bool:
    track = await session.get(Track, track_id)
    if track is None:
        return False
    track.moderation_status = status
    await session.commit()
    return True


"""Дополнение минусов: исполнитель и обложка (19.09, решение владельца).

Минусы приезжают из ТГ-канала @zvyagaminus одним аудио без метаданных: у 20 из
491 исполнитель «Неизвестный», обложки нет ни у одного. В плеере это серый
квадрат и пустая подпись (скрины владельца 19.09).

Берём недостающее из SoundCloud: ищем по «исполнитель + название» и принимаем
кандидата, только если название реально совпало (`best_match` с порогом). Иначе
минус «Гантеля» получил бы обложку случайной песни — это хуже заглушки.

⚠️ Исполнителя записываем только там, где его нет: у минуса он значит «чей бит»,
и перетирать уже заполненное догадкой источника нельзя.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Instrumental

logger = logging.getLogger(__name__)

UNKNOWN_ARTISTS = ("Неизвестный", "Исполнитель", "Unknown", "")
# «Не нашлось» — состояние временное: трек могли залить позже. Через две недели
# пробуем снова, как в ночном ремонте каталога.
RETRY_AFTER = timedelta(days=14)
MIN_SCORE = 0.6  # выше обычного порога поиска: ошибка тут видна каждому в плеере


def needs_enrich(item: Instrumental) -> bool:
    return not item.cover_url or (item.artist or "").strip() in UNKNOWN_ARTISTS


async def due_minuses(
    session: AsyncSession, limit: int, now: datetime | None = None
) -> list[Instrumental]:
    """Минусы без обложки или без исполнителя, которыми давно не занимались."""
    now = now or datetime.utcnow()
    stale = now - RETRY_AFTER
    stmt = (
        select(Instrumental)
        .where(
            or_(
                Instrumental.cover_url.is_(None),
                Instrumental.artist.in_(UNKNOWN_ARTISTS),
            ),
            or_(
                Instrumental.enrich_checked_at.is_(None),
                Instrumental.enrich_checked_at < stale,
            ),
        )
        .order_by(Instrumental.enrich_checked_at.is_(None).desc(), Instrumental.id)
        .limit(limit)
    )
    return list((await session.scalars(stmt)).all())


def _query(item: Instrumental) -> str:
    artist = (item.artist or "").strip()
    if artist in UNKNOWN_ARTISTS:
        artist = ""
    return f"{artist} {item.title}".strip()


def find_match(item: Instrumental):
    """Кандидат SoundCloud под этот минус. None — не нашли ничего похожего."""
    from app.services.soundcloud_api import search_tracks
    from app.services.track_lookup.ranking import best_match

    query = _query(item)
    if not query:
        return None
    try:
        candidates = search_tracks(query, limit=5)
    except Exception:  # noqa: BLE001 — источник отвалился, попробуем в другую ночь
        logger.warning("Минусы: поиск «%s» не удался", query, exc_info=True)
        return None
    return best_match(query, candidates, min_score=MIN_SCORE)


async def enrich_minus(
    session: AsyncSession, item: Instrumental, now: datetime | None = None
) -> bool:
    """Дописывает минусу обложку и исполнителя. True — что-то изменилось.

    Отметку «занимались» ставим в любом случае и ДО следующей ночи: иначе
    безнадёжные минусы каждый раз оказывались бы первыми в очереди.
    """
    match = find_match(item)
    changed = False
    if match is not None:
        if not item.cover_url and match.cover_url:
            item.cover_url = match.cover_url
            changed = True
        if (item.artist or "").strip() in UNKNOWN_ARTISTS and (match.artist or "").strip():
            item.artist = match.artist.strip()
            changed = True
    item.enrich_checked_at = now or datetime.utcnow()
    await session.commit()
    return changed

"""Массовое тегирование настроения треков для рекомендаций.

Использование:
    python -m app.cli.set_mood <mood> <запрос>       # по подстроке в названии/исполнителе
    python -m app.cli.set_mood <mood> --untagged     # все треки без настроения
    python -m app.cli.set_mood <mood> <запрос> --dry # только показать, без записи

mood: happy | sad | energetic | calm | love
"""
import argparse
import asyncio
import logging

from sqlalchemy import or_, select

from app.db.base import session_factory
from app.db.models import Track
from app.services.recommendations import VALID_MOODS

logger = logging.getLogger("set_mood")


async def run(mood: str, query: str | None, untagged: bool, dry: bool) -> None:
    stmt = select(Track)
    if untagged:
        stmt = stmt.where(Track.mood.is_(None))
    else:
        pattern = f"%{query}%"
        stmt = stmt.where(or_(Track.title.ilike(pattern), Track.artist.ilike(pattern)))

    async with session_factory() as session:
        tracks = list((await session.scalars(stmt)).all())
        for track in tracks:
            logger.info("%s — %s (%s → %s)", track.artist, track.title, track.mood or "—", mood)
            if not dry:
                track.mood = mood
        if not dry:
            await session.commit()

    logger.info("%s: %s треков", "Найдено (dry-run)" if dry else "Обновлено", len(tracks))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Массовое тегирование настроения треков")
    parser.add_argument("mood", choices=sorted(VALID_MOODS), help="Настроение")
    parser.add_argument("query", nargs="?", help="Подстрока в названии или исполнителе")
    parser.add_argument("--untagged", action="store_true", help="Все треки без настроения")
    parser.add_argument("--dry", action="store_true", help="Показать без записи")
    args = parser.parse_args()

    if not args.untagged and not args.query:
        parser.error("нужен <запрос> или --untagged")

    asyncio.run(run(args.mood, args.query, args.untagged, args.dry))


if __name__ == "__main__":
    main()

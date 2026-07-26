"""Восстановление обложек треков без картинки (запрос владельца).

Парсер иногда заводил треки без обложки. Здесь для каждого такого трека ищем
обложку на SoundCloud по «Исполнитель Название» и проставляем cover_url.

  python -m app.cli.recover_covers [--limit N]

Сеть SoundCloud (yt-dlp) — идём последовательно с паузами (анти-бан уже в клиенте).
"""
import argparse
import asyncio
import logging

from sqlalchemy import or_, select

from app.db.base import session_factory
from app.db.models import Track
from app.services.soundcloud import fetch_cover_url

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("recover-covers")


async def _run(limit: int) -> None:
    async with session_factory() as session:
        tracks = list(
            (
                await session.scalars(
                    select(Track)
                    .where(or_(Track.cover_url.is_(None), Track.cover_url == ""))
                    .limit(limit)
                )
            ).all()
        )
        logger.info("Треков без обложки к обработке: %s", len(tracks))
        fixed = 0
        for track in tracks:
            cover = await asyncio.to_thread(fetch_cover_url, f"{track.artist} {track.title}")
            if cover:
                track.cover_url = cover
                fixed += 1
                logger.info("Обложка найдена: %s — %s", track.artist, track.title)
        await session.commit()
        logger.info("Готово: восстановлено обложек — %s из %s", fixed, len(tracks))


def main() -> None:
    parser = argparse.ArgumentParser(description="Восстановить обложки треков без картинки")
    parser.add_argument("--limit", type=int, default=500)
    args = parser.parse_args()
    asyncio.run(_run(args.limit))


if __name__ == "__main__":
    main()

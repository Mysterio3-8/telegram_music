"""Подбор границ фильтра «только треки» по реальной базе.

  python -m app.cli.duration_stats            # распределение + что отсечётся
  python -m app.cli.duration_stats --show 20  # + примеры коротких и длинных

Показывает, сколько треков попадёт под нож при разных границах, чтобы выбрать
search_min_seconds / search_max_seconds осознанно, а не наугад.
"""
import argparse
import asyncio

from sqlalchemy import func, select

from app.db.base import session_factory
from app.db.models import Track

# Пары (мин, макс) в секундах — варианты на выбор владельцу
PRESETS = [
    (45, 900),
    (60, 720),
    (90, 600),
    (120, 480),
]

BUCKETS = [
    (0, 30, "до 30 сек — обрезки, джинглы"),
    (30, 60, "30-60 сек — скиты, интро"),
    (60, 120, "1-2 мин — короткие треки"),
    (120, 300, "2-5 мин — основная музыка"),
    (300, 600, "5-10 мин — длинные треки, ремиксы"),
    (600, 1200, "10-20 мин — миксы, сеты"),
    (1200, 3600, "20-60 мин — подкасты, альбомы"),
    (3600, 10**9, "больше часа — точно не трек"),
]


async def _stats(show: int) -> None:
    async with session_factory() as session:
        total = (await session.scalar(select(func.count()).select_from(Track))) or 0
        if not total:
            print("В базе нет треков")
            return

        print(f"Всего треков: {total}\n")
        print("Распределение по длительности:")
        for low, high, label in BUCKETS:
            count = (
                await session.scalar(
                    select(func.count())
                    .select_from(Track)
                    .where(Track.duration >= low, Track.duration < high)
                )
            ) or 0
            share = count * 100 / total
            bar = "█" * int(share / 2)
            print(f"  {label:<38} {count:>6} ({share:5.1f}%) {bar}")

        print("\nЧто отсечётся при разных границах:")
        for low, high in PRESETS:
            cut = (
                await session.scalar(
                    select(func.count())
                    .select_from(Track)
                    .where((Track.duration < low) | (Track.duration > high))
                )
            ) or 0
            share = cut * 100 / total
            print(
                f"  {low:>4} сек — {high // 60:>2} мин: отсечёт {cut:>6} ({share:5.1f}%), "
                f"останется {total - cut}"
            )

        if show:
            print(f"\nСамые короткие ({show}):")
            rows = await session.scalars(
                select(Track).order_by(Track.duration).limit(show)
            )
            for track in rows:
                print(f"  {track.duration:>5} сек  {track.artist} — {track.title}")

            print(f"\nСамые длинные ({show}):")
            rows = await session.scalars(
                select(Track).order_by(Track.duration.desc()).limit(show)
            )
            for track in rows:
                print(f"  {track.duration:>5} сек  {track.artist} — {track.title}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Подбор границ фильтра длительности")
    parser.add_argument("--show", type=int, default=0, help="показать N примеров с краёв")
    args = parser.parse_args()
    asyncio.run(_stats(args.show))


if __name__ == "__main__":
    main()

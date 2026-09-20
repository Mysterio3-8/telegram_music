"""Ночное дополнение минусов: исполнитель и обложка (19.09).

    python -m app.cli.enrich_minuses [--limit 40] [--dry]

Почему с лимитом: каждый минус — это запрос к SoundCloud, а не локальная работа.
40 за ночь разбирают весь накопленный хвост (491 минус, из них без обложки все)
примерно за две недели и не мешают ни одному живому запросу.
"""
import argparse
import asyncio

from app.db.base import session_factory
from app.services.minus_enrich import due_minuses, enrich_minus, find_match


async def _run(limit: int, dry: bool) -> None:
    async with session_factory() as session:
        items = await due_minuses(session, limit)
        print(f"К дополнению: {len(items)}")
        filled = 0
        for item in items:
            if dry:
                match = find_match(item)
                print(f"  {item.id} «{item.artist} — {item.title}» → {match.title if match else '—'}")
                continue
            if await enrich_minus(session, item):
                filled += 1
                print(f"  {item.id} → {item.artist}, обложка {'есть' if item.cover_url else 'нет'}")
        if not dry:
            print(f"Дополнено: {filled} из {len(items)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Дополнить минусы исполнителем и обложкой")
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument("--dry", action="store_true", help="только показать, что нашлось")
    args = parser.parse_args()
    asyncio.run(_run(args.limit, args.dry))


if __name__ == "__main__":
    main()

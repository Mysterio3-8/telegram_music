"""Управление артистами: сид из CSV владельца, источники закачки, аватары.

CSV: `name;soundcloud_url` (артисты/ARTISTS.csv).

  python -m app.cli.artists seed артисты/ARTISTS.csv         # завести артистов
  python -m app.cli.artists add-sources артисты/ARTISTS.csv  # источники закачки
  python -m app.cli.artists fetch-photos --limit 50          # аватары со страниц
  python -m app.cli.artists stats
"""
import argparse
import asyncio
import csv
import re
import time
import urllib.request

from app.db.base import session_factory
from app.services.artist_entities import (
    artists_without_photo,
    count_artists,
    set_artist_photo,
    upsert_artist,
)
from app.services.soundcloud_sources import add_source

_OG_IMAGE = re.compile(r'property="og:image"\s+content="([^"]+)"')
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0"


def _read_csv(path: str) -> list[tuple[str, str]]:
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";")
        return [
            (row["name"].strip(), row["soundcloud_url"].strip())
            for row in reader
            if row.get("name") and row.get("soundcloud_url")
        ]


async def _seed(path: str) -> None:
    created = updated = 0
    async with session_factory() as session:
        for name, url in _read_csv(path):
            _, is_new = await upsert_artist(session, name, soundcloud_url=url)
            created += is_new
            updated += not is_new
    print(f"Артистов создано: {created}, уже были: {updated}")


async def _add_sources(path: str) -> None:
    added = existed = 0
    async with session_factory() as session:
        for name, url in _read_csv(path):
            source, is_new = await add_source(session, url, title=name)
            added += is_new
            existed += not is_new
    print(f"Источников добавлено: {added}, уже были: {existed}")


def _fetch_og_image(url: str) -> str | None:
    request = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(request, timeout=15) as response:
        html = response.read(400_000).decode("utf-8", errors="ignore")
    match = _OG_IMAGE.search(html)
    return match.group(1) if match else None


async def _fetch_photos(limit: int) -> None:
    """Аватар = og:image страницы профиля SoundCloud. С паузой — не долбим."""
    done = failed = 0
    async with session_factory() as session:
        candidates = await artists_without_photo(session, limit)
        for artist in candidates:
            try:
                photo = _fetch_og_image(artist.soundcloud_url)
            except Exception:  # noqa: BLE001 — сеть/404: пропускаем, добьём следующим прогоном
                photo = None
            if photo:
                await set_artist_photo(session, artist.id, photo)
                done += 1
            else:
                failed += 1
            time.sleep(1.5)
    print(f"Аватары получены: {done}, не удалось: {failed}, кандидатов было: {len(candidates)}")


async def _stats() -> None:
    async with session_factory() as session:
        total = await count_artists(session)
        without_photo = len(await artists_without_photo(session, 100000))
    print(f"Артистов всего: {total}, без фото: {without_photo}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Артисты: сид, источники, аватары")
    sub = parser.add_subparsers(dest="command", required=True)
    seed = sub.add_parser("seed")
    seed.add_argument("csv")
    sources = sub.add_parser("add-sources")
    sources.add_argument("csv")
    photos = sub.add_parser("fetch-photos")
    photos.add_argument("--limit", type=int, default=50)
    sub.add_parser("stats")

    args = parser.parse_args()
    if args.command == "seed":
        asyncio.run(_seed(args.csv))
    elif args.command == "add-sources":
        asyncio.run(_add_sources(args.csv))
    elif args.command == "fetch-photos":
        asyncio.run(_fetch_photos(args.limit))
    else:
        asyncio.run(_stats())


if __name__ == "__main__":
    main()

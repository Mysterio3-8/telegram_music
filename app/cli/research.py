"""Исследователь мирового каталога (SPEC-КАТАЛОГ §3-4).

  python -m app.cli.research country RU --limit 200          # артисты страны из MusicBrainz
  python -m app.cli.research search "phonk" --limit 100      # по произвольному Lucene-запросу
  python -m app.cli.research attach-sources --limit 500      # привязать источники закачки
  python -m app.cli.research enrich --limit 500              # дообогатить артистов без mbid (жанры/страна/фото)
  python -m app.cli.research stats

⚠️ enrich и country/search бьют в MusicBrainz с общим лимитом 1 req/sec НА IP —
не запускать два прогона параллельно (троттлинг у каждого процесса свой).

Темп ограничен MusicBrainz (1 req/sec): ~2 запроса на артиста → ~25 артистов/мин.
Запускать фоном на VPS: nohup python -m app.cli.research country RU --limit 1000 &
"""
import argparse
import asyncio

from sqlalchemy import func, select

from app.db.base import session_factory
from app.db.models import Artist
from app.services import deezer, musicbrainz
from app.services.artist_research import (
    artists_without_source,
    attach_source_for_artist,
    save_researched,
)

SEARCH_PAGE_SIZE = 100
MIN_SEARCH_SCORE = 60  # ниже — мусорные совпадения поиска MusicBrainz


async def _research(query: str, limit: int, offset: int, with_photos: bool) -> None:
    created = updated = failed = 0
    processed = 0
    async with session_factory() as session:
        while processed < limit:
            page = musicbrainz.search_artists(
                query, limit=min(SEARCH_PAGE_SIZE, limit - processed), offset=offset + processed
            )
            if not page:
                break
            for brief in page:
                processed += 1
                if brief.get("score", 0) < MIN_SEARCH_SCORE:
                    continue
                try:
                    details = musicbrainz.artist_details(brief["id"])
                    researched = musicbrainz.parse_artist(details)
                    photo = banner = None
                    deezer_id = None
                    if with_photos:
                        try:
                            found = deezer.find_artist(researched.name)
                        except Exception:  # noqa: BLE001 — сеть Deezer: фото добьём позже
                            found = None
                        if found:
                            photo = banner = found.picture_xl
                            deezer_id = found.id
                    _, is_new = await save_researched(
                        session,
                        researched,
                        photo_url=photo,
                        banner_url=banner,
                        deezer_id=deezer_id,
                    )
                    created += is_new
                    updated += not is_new
                except Exception as error:  # noqa: BLE001 — один артист не роняет прогон
                    failed += 1
                    print(f"  ! {brief.get('name')}: {error}")
                if processed % 25 == 0:
                    print(f"…{processed}/{limit} (создано {created}, обновлено {updated})")
    print(f"Готово: создано {created}, обновлено {updated}, ошибок {failed}, просмотрено {processed}")


ENRICH_MIN_SCORE = 90  # точное совпадение имени — чужой артист хуже, чем никакой


async def _enrich(limit: int, with_photos: bool) -> None:
    """Дообогащение уже заведённых артистов (сид владельца): поиск в MusicBrainz
    по точному имени → жанры, страна, ссылки, алиасы; фото — Deezer."""
    enriched = skipped = failed = 0
    async with session_factory() as session:
        rows = await session.scalars(
            select(Artist).where(Artist.mbid.is_(None)).order_by(Artist.id).limit(limit)
        )
        for artist in list(rows.all()):
            try:
                found = musicbrainz.search_artists(f'artist:"{artist.name}"', limit=3)
                best = next(
                    (
                        item
                        for item in found
                        if item.get("score", 0) >= ENRICH_MIN_SCORE
                        and item.get("name", "").strip().lower() == artist.name.strip().lower()
                    ),
                    None,
                )
                if best is None:
                    skipped += 1
                    continue
                details = musicbrainz.artist_details(best["id"])
                researched = musicbrainz.parse_artist(details)
                photo = None
                deezer_id = None
                if with_photos and not artist.photo_url:
                    try:
                        deezer_found = deezer.find_artist(artist.name)
                    except Exception:  # noqa: BLE001 — сеть Deezer: фото добьём позже
                        deezer_found = None
                    if deezer_found:
                        photo = deezer_found.picture_xl
                        deezer_id = deezer_found.id
                await save_researched(
                    session, researched, photo_url=photo, banner_url=photo, deezer_id=deezer_id
                )
                enriched += 1
            except Exception as error:  # noqa: BLE001 — один артист не роняет прогон
                failed += 1
                print(f"  ! {artist.name}: {error}")
    print(f"Обогащено: {enriched}, не найдено в MusicBrainz: {skipped}, ошибок: {failed}")


async def _attach_sources(limit: int) -> None:
    counts = {"soundcloud": 0, "youtube": 0, "no_source": 0}
    async with session_factory() as session:
        for artist in await artists_without_source(session, limit):
            status = await attach_source_for_artist(session, artist)
            counts[status] += 1
    print(
        f"SoundCloud: {counts['soundcloud']}, YouTube: {counts['youtube']}, "
        f"без источника: {counts['no_source']}"
    )


async def _stats() -> None:
    async with session_factory() as session:
        total = (await session.scalar(select(func.count()).select_from(Artist))) or 0
        with_mbid = (
            await session.scalar(
                select(func.count()).select_from(Artist).where(Artist.mbid.is_not(None))
            )
        ) or 0
        rows = await session.execute(
            select(Artist.source_status, func.count()).group_by(Artist.source_status)
        )
        by_status = dict(rows.all())
    print(f"Артистов: {total}, из MusicBrainz: {with_mbid}, источники: {by_status}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Исследователь каталога артистов")
    sub = parser.add_subparsers(dest="command", required=True)

    country = sub.add_parser("country", help="артисты страны (ISO-код: RU, US, KR…)")
    country.add_argument("code")
    country.add_argument("--limit", type=int, default=200)
    country.add_argument("--offset", type=int, default=0)
    country.add_argument("--no-photos", action="store_true")

    search = sub.add_parser("search", help="произвольный Lucene-запрос MusicBrainz")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=100)
    search.add_argument("--offset", type=int, default=0)
    search.add_argument("--no-photos", action="store_true")

    attach = sub.add_parser("attach-sources")
    attach.add_argument("--limit", type=int, default=500)

    enrich = sub.add_parser("enrich")
    enrich.add_argument("--limit", type=int, default=500)
    enrich.add_argument("--no-photos", action="store_true")

    sub.add_parser("stats")

    args = parser.parse_args()
    if args.command == "country":
        query = f"country:{args.code.upper()}"
        asyncio.run(_research(query, args.limit, args.offset, not args.no_photos))
    elif args.command == "search":
        asyncio.run(_research(args.query, args.limit, args.offset, not args.no_photos))
    elif args.command == "attach-sources":
        asyncio.run(_attach_sources(args.limit))
    elif args.command == "enrich":
        asyncio.run(_enrich(args.limit, not args.no_photos))
    else:
        asyncio.run(_stats())


if __name__ == "__main__":
    main()

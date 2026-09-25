"""Ночное дообогащение каталога: карточки артистов и альбомы (22.09).

    python -m app.cli.catalog_enrich                     # оба прохода
    python -m app.cli.catalog_enrich --artists 50 --tracks 200

1. Непривязанные к артисту строки получают карточку — с каноническим именем и
   фото из Deezer, если он артиста знает (`artist_resolve`).
2. Трекам SoundCloud без альбома или обложки дописываются данные из карточки
   трека в источнике (`track_meta_enrich`).

Темп задан нагрузкой, а не желанием: Deezer и SoundCloud — это сеть, и в ночном
окне (00:00–02:00 UTC) хватает сотни-другой запросов. Каталог дообогащается за
несколько ночей, и каждая следующая ночь берёт следующих — отметки не дают
возвращаться к уже сверенному.
"""
import argparse
import asyncio

from app.db.base import session_factory


async def _run(artists: int, tracks: int) -> None:
    from app.services.artist_resolve import resolve_unbound
    from app.services.track_meta_enrich import enrich_tracks

    if artists:
        async with session_factory() as session:
            report = await resolve_unbound(session, limit=artists)
        print(
            f"Артисты: готовых карточек {report.bound_existing}, новых с фото "
            f"{report.created_with_photo}, без фото {report.created_plain}; "
            f"привязано треков {report.tracks_bound}, пропущено {report.skipped}"
        )
    if tracks:
        async with session_factory() as session:
            report = await enrich_tracks(session, limit=tracks)
        print(
            f"Треки: сверено {report.checked}, альбомов +{report.albums}, "
            f"обложек +{report.covers}, источник не ответил {report.failed}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Дообогащение каталога: артисты и альбомы")
    parser.add_argument("--artists", type=int, default=50, help="сколько строк артистов за прогон")
    parser.add_argument("--tracks", type=int, default=200, help="сколько треков сверить с источником")
    args = parser.parse_args()
    asyncio.run(_run(args.artists, args.tracks))


if __name__ == "__main__":
    main()

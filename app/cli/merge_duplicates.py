"""Слияние дубликатов каталога.

    python -m app.cli.merge_duplicates                 # только показать, ничего не менять
    python -m app.cli.merge_duplicates --apply
    python -m app.cli.merge_duplicates --apply --limit 20

🔴 Откуда взялись дубли. `find_duplicate` сравнивал `lower(Track.title)` с уже
понижённой в Питоне строкой, а SQLite `lower()` понижает только ASCII — для
кириллицы совпадения не было никогда, и каждый повторный импорт заводил копию
(замер 16.08: 140 пар, 131 заведён после перехода на живой поиск). Сам дедуп
починен; эта команда разбирает то, что он успел накопить.

⚠️ **Слияние, а не удаление.** Просто снести лишние строки нельзя: они лежат в
чужих библиотеках и плейлистах, и человек молча потерял бы трек из подборки —
восстанавливать было бы нечего. Поэтому связи сначала ПЕРЕНОСЯТСЯ на
оставляемый трек, и только осиротевшая запись удаляется. В июле чистка каталога
по другому критерию едва не снесла 93% собранного пользователями — тот случай и
задал это правило.

Кого оставляем: сперва трек с живым `tg_file_id` (иначе слили бы в пустышку),
затем самый слушаемый, затем самый старый — у старого больше шансов быть
привязанным в чужих плейлистах. Полезные поля (`source_url`, обложка, архив)
с удаляемых копий переносятся на оставляемый, если у него их нет.
"""
import argparse
import asyncio
import logging
from collections import defaultdict

from sqlalchemy import delete, func, select, update

from app.db.base import session_factory
from app.db.models import (
    Lyrics,
    MixHistory,
    PlaylistTrack,
    Track,
    TrackEvent,
    Upload,
    UserLibrary,
)

logger = logging.getLogger(__name__)

# Насколько может расходиться длительность у одной и той же записи. Та же
# величина, что в дедупе при импорте: разные по длине версии — разные треки
# (у «Александр Маршал — Беззаботный» четыре копии на 261, 218, 215 и 233 сек).
from app.services.uploads import DUPLICATE_DURATION_TOLERANCE


async def _plays(session) -> dict[int, int]:
    rows = (
        await session.execute(
            select(TrackEvent.track_id, func.count()).group_by(TrackEvent.track_id)
        )
    ).all()
    return {track_id: n for track_id, n in rows}


def _group_key(track: Track) -> tuple | None:
    """Ключ группировки. None — трек в слияние не участвует.

    Ссылка источника — точный ключ. `search_index` — нормализованный в Питоне
    «артист название», по нему и сверяется дедуп при импорте; длительность
    округляем в корзины, чтобы допуск работал как в импорте.
    """
    if track.source_url:
        return ("url", track.source_url)
    if track.search_index and track.duration:
        bucket = round(track.duration / (DUPLICATE_DURATION_TOLERANCE * 2 or 1))
        return ("meta", track.search_index, bucket)
    return None


def _keeper(group: list[Track], plays: dict[int, int]) -> Track:
    """Кого оставляем. Живой файл важнее всего: слить в пустышку — потерять трек."""
    return sorted(
        group,
        key=lambda t: (
            0 if t.tg_file_id else 1,
            -plays.get(t.id, 0),
            t.id,
        ),
    )[0]


async def _merge_group(session, keeper: Track, losers: list[Track]) -> None:
    ids = [t.id for t in losers]

    # Поля, которых у оставляемого нет, — забираем с копий: обидно потерять
    # обложку или ссылку источника только потому, что она досталась дубликату.
    for field in ("source_url", "cover_url", "storage_path", "album", "tg_file_id"):
        if getattr(keeper, field, None):
            continue
        for loser in losers:
            value = getattr(loser, field, None)
            if value:
                setattr(keeper, field, value)
                break

    # Библиотеки и плейлисты — составной первичный ключ, поэтому переносим
    # только то, чего у оставляемого ещё нет, остальное просто удаляем.
    owned = set(
        (await session.scalars(
            select(UserLibrary.user_id).where(UserLibrary.track_id == keeper.id)
        )).all()
    )
    for user_id in (await session.scalars(
        select(UserLibrary.user_id).where(UserLibrary.track_id.in_(ids))
    )).all():
        if user_id not in owned:
            session.add(UserLibrary(user_id=user_id, track_id=keeper.id))
            owned.add(user_id)
    await session.execute(delete(UserLibrary).where(UserLibrary.track_id.in_(ids)))

    in_playlists = set(
        (await session.scalars(
            select(PlaylistTrack.playlist_id).where(PlaylistTrack.track_id == keeper.id)
        )).all()
    )
    for row in (await session.scalars(
        select(PlaylistTrack).where(PlaylistTrack.track_id.in_(ids))
    )).all():
        if row.playlist_id not in in_playlists:
            session.add(
                PlaylistTrack(
                    playlist_id=row.playlist_id,
                    track_id=keeper.id,
                    position=row.position,
                )
            )
            in_playlists.add(row.playlist_id)
    await session.execute(delete(PlaylistTrack).where(PlaylistTrack.track_id.in_(ids)))

    # Статистика и загрузки просто переезжают: ограничений на пару нет
    await session.execute(
        update(TrackEvent).where(TrackEvent.track_id.in_(ids)).values(track_id=keeper.id)
    )
    await session.execute(
        update(Upload).where(Upload.track_id.in_(ids)).values(track_id=keeper.id)
    )
    await session.execute(
        update(MixHistory).where(MixHistory.track_id.in_(ids)).values(track_id=keeper.id)
    )

    # Текст песни: один на трек (track_id — первичный ключ). Переносим, только
    # если у оставляемого его нет, иначе затрём чужой правкой.
    if await session.get(Lyrics, keeper.id) is None:
        found = (await session.scalars(
            select(Lyrics).where(Lyrics.track_id.in_(ids)).limit(1)
        )).first()
        if found is not None:
            session.add(Lyrics(track_id=keeper.id, text=found.text, source=found.source))
    await session.execute(delete(Lyrics).where(Lyrics.track_id.in_(ids)))

    await session.execute(delete(Track).where(Track.id.in_(ids)))
    await session.commit()


async def run(apply: bool, limit: int | None) -> int:
    async with session_factory() as session:
        tracks = list((await session.scalars(select(Track))).all())
        plays = await _plays(session)

        groups: dict[tuple, list[Track]] = defaultdict(list)
        for track in tracks:
            key = _group_key(track)
            if key is not None:
                groups[key].append(track)
        dupes = [g for g in groups.values() if len(g) > 1]
        dupes.sort(key=lambda g: -len(g))
        if limit:
            dupes = dupes[:limit]

        extra = sum(len(g) - 1 for g in dupes)
        print(f"групп дубликатов: {len(dupes)}, лишних записей: {extra}")
        if not dupes:
            return 0

        # Сколько людей это заденет — главное число для решения
        loser_ids = [t.id for g in dupes for t in g if t is not _keeper(g, plays)]
        in_lib = await session.scalar(
            select(func.count()).select_from(UserLibrary).where(
                UserLibrary.track_id.in_(loser_ids))
        ) or 0
        in_pl = await session.scalar(
            select(func.count()).select_from(PlaylistTrack).where(
                PlaylistTrack.track_id.in_(loser_ids))
        ) or 0
        print(f"из них лежат в библиотеках: {in_lib}, в плейлистах: {in_pl} — связи перенесём")

        for group in dupes[:10]:
            keep = _keeper(group, plays)
            others = [t for t in group if t is not keep]
            print(f"\n  ОСТАВИТЬ id={keep.id} «{keep.artist} — {keep.title}» "
                  f"(файл={'есть' if keep.tg_file_id else 'НЕТ'}, "
                  f"прослушиваний={plays.get(keep.id, 0)})")
            for t in others:
                print(f"    слить id={t.id} (файл={'есть' if t.tg_file_id else 'нет'}, "
                      f"прослушиваний={plays.get(t.id, 0)})")
        if len(dupes) > 10:
            print(f"\n  … и ещё групп: {len(dupes) - 10}")

        if not apply:
            print("\nЭто пробный прогон — база не изменена. Чтобы слить: --apply")
            return 0

        merged = 0
        for group in dupes:
            keep = _keeper(group, plays)
            losers = [t for t in group if t is not keep]
            await _merge_group(session, keep, losers)
            merged += len(losers)
        print(f"\nСлито записей: {merged}")
        logger.info("Слияние дубликатов: убрано %s записей", merged)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Слияние дубликатов каталога")
    parser.add_argument("--apply", action="store_true", help="менять базу, а не только показывать")
    parser.add_argument("--limit", type=int, help="обработать не больше N групп")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    return asyncio.run(run(args.apply, args.limit))


if __name__ == "__main__":
    raise SystemExit(main())

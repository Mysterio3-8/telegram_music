"""Ужать базу: выкинуть то, что больше не работает на сервис.

Замер 12.08 (app.cli.db_size): база 63 МБ на 7372 трека, то есть 8.8 КБ на трек.
Но сами треки в этом весе занимают 7.6 МБ (около килобайта на трек), а 39.7 МБ
(63% всей базы!) — это `youtube_imports` с четырьмя индексами: журнал массового
парсера, выключенного 27.07 решением владельца. Он хранит по строке на КАЖДОЕ
увиденное видео, включая отклонённые и упавшие, и его роль — не качать одно и то
же при повторном скане. Сканов больше нет.

Ещё 6.2 МБ — индекс отпечатков: живой поиск их не считает (fpcalc декодирует
трек целиком, а дубликат мы ловим по ссылке источника), значит для новых треков
поле пустое, а старые значения только занимают место.

По умолчанию НИЧЕГО не удаляет — показывает, что будет. Удаляет по --apply.

    python -m app.cli.prune_db                    # только показать
    python -m app.cli.prune_db --apply            # почистить и сжать файл
    python -m app.cli.prune_db --apply --keep-fingerprints   # отпечатки не трогать

⚠️ Записи, привязанные к живым трекам (`track_id` не пуст), сохраняются всегда:
по ним видно, откуда трек приехал.
"""
import argparse
import asyncio

from sqlalchemy import func, select, text, update

from app.db.base import session_factory
from app.db.models import Track, YoutubeImport


async def _counts() -> dict[str, int]:
    async with session_factory() as session:
        orphan = await session.scalar(
            select(func.count()).select_from(YoutubeImport).where(YoutubeImport.track_id.is_(None))
        )
        linked = await session.scalar(
            select(func.count()).select_from(YoutubeImport).where(YoutubeImport.track_id.is_not(None))
        )
        fingerprints = await session.scalar(
            select(func.count()).select_from(Track).where(Track.fingerprint.is_not(None))
        )
    return {
        "журнал парсера без трека": orphan or 0,
        "журнал парсера с треком (сохраним)": linked or 0,
        "треков с отпечатком": fingerprints or 0,
    }


async def main() -> None:
    parser = argparse.ArgumentParser(description="Чистка и сжатие базы.")
    parser.add_argument("--apply", action="store_true", help="действительно удалить")
    parser.add_argument(
        "--keep-fingerprints", action="store_true", help="не стирать отпечатки треков"
    )
    args = parser.parse_args()

    for name, value in (await _counts()).items():
        print(f"{name}: {value}")

    if not args.apply:
        print("\nЭто пробный прогон. Чтобы удалить — повторите с --apply")
        return

    async with session_factory() as session:
        result = await session.execute(
            YoutubeImport.__table__.delete().where(YoutubeImport.track_id.is_(None))
        )
        print(f"Удалено записей журнала: {result.rowcount}")

        if not args.keep_fingerprints:
            cleared = await session.execute(
                update(Track).where(Track.fingerprint.is_not(None)).values(fingerprint=None)
            )
            print(f"Стёрто отпечатков: {cleared.rowcount}")
        await session.commit()

    # VACUUM освобождает место в файле: без него страницы остаются за базой,
    # и на диске ничего не меняется. Отдельным соединением — внутри транзакции
    # SQLite его не выполняет.
    async with session_factory() as session:
        await session.execute(text("VACUUM"))
    print("Файл базы сжат (VACUUM). Проверьте: python -m app.cli.db_size")


if __name__ == "__main__":
    asyncio.run(main())

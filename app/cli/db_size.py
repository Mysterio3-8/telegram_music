"""Из чего состоит база: сколько занимает каждая таблица и каждый индекс.

Прежде чем ужимать, надо знать, что именно тяжёлое. Прошлый раз догадка стоила
дорого: индекс отпечатков весил 128 МБ — почти столько же, сколько вся таблица
треков, и обнаружилось это только замером.

    python -m app.cli.db_size

Работает на SQLite (у нас прод на ней). Нужен модуль dbstat — он собран в
стандартной сборке Python; если его нет, скрипт честно скажет об этом.
"""
import asyncio

from sqlalchemy import text

from app.db.base import session_factory


def _human(size_bytes: int) -> str:
    for unit in ("Б", "КБ", "МБ", "ГБ"):
        if size_bytes < 1024 or unit == "ГБ":
            return f"{size_bytes:.0f} {unit}" if unit == "Б" else f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} ГБ"


async def main() -> None:
    async with session_factory() as session:
        try:
            rows = (
                await session.execute(
                    text(
                        "SELECT name, SUM(pgsize) AS bytes FROM dbstat "
                        "GROUP BY name ORDER BY bytes DESC"
                    )
                )
            ).all()
        except Exception as exc:  # noqa: BLE001 — нет dbstat или не SQLite
            print(f"Замер недоступен: {exc}")
            return

        tracks = await session.scalar(text("SELECT count(*) FROM tracks")) or 0
        total = sum(row[1] or 0 for row in rows)

        print(f"Всего: {_human(total)}, треков: {tracks}")
        if tracks:
            print(f"На один трек: {_human(total / tracks)}\n")
        print(f"{'объект':<40} {'размер':>10} {'доля':>6}")
        print("-" * 58)
        for name, size in rows:
            size = size or 0
            if size < 1024 * 100:  # мелочь не засоряет вывод
                continue
            print(f"{name:<40} {_human(size):>10} {size / total * 100:>5.1f}%")


if __name__ == "__main__":
    asyncio.run(main())

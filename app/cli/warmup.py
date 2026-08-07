"""Прогрев каталога: заранее минтим треки в архивный канал.

Зачем. Поиск теперь занимает 0.22 сек, но если трека нет в базе, после поиска
его надо СКАЧАТЬ — а это ещё ~8.5 сек, и здесь предел ставит источник. Уже
заминченный трек уходит человеку мгновенно, по file_id, вообще без сети.
Значит единственный способ дать «мгновенно» — иметь трек заранее.

Аудио лежит у Telegram, наш диск оно не занимает. Занимает база: ~9 КБ на трек
(замер: 7240 треков = 65 МБ). Отсюда потолок — см. --help.

    python -m app.cli.warmup --popular 300        # что люди реально ищут
    python -m app.cli.warmup --file queries.txt   # свой список, запрос на строку
    python -m app.cli.warmup --popular 50 --dry   # только показать, что будет

Идемпотентен: трек, который уже в базе, пропускается — прогон можно прерывать и
запускать заново.
"""
import argparse
import asyncio
import logging
import time

from aiogram import Bot
from sqlalchemy import func, select

from app.config import settings
from app.db.base import session_factory
from app.db.models import SearchQuery
from app.services.catalog_import import find_existing_track, import_via_telegram_mint
from app.services.disk import enough_free_disk, free_mb
from app.services.track_lookup import find_track
from app.services.track_lookup.importer import download_candidate
from app.services.youtube.downloader import fetch_thumbnail, fetch_telegram_thumbnail

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger("warmup")

# Telegram режет ботам темп отправки в один чат. 4 секунды между треками — это
# ~15 в минуту, заведомо ниже потолка: прогрев идёт фоном, торопиться некуда,
# а поймать бан на архивном канале означает остановить минт вообще весь.
DELAY_SECONDS = 4.0


async def popular_queries(limit: int) -> list[str]:
    """Реальные запросы людей, самые частые сверху — их и греем в первую очередь."""
    async with session_factory() as session:
        rows = await session.execute(
            select(SearchQuery.query, func.count().label("hits"))
            .group_by(SearchQuery.query)
            .order_by(func.count().desc())
            .limit(limit)
        )
        return [row[0] for row in rows]


def read_queries(path: str, limit: int) -> list[str]:
    with open(path, encoding="utf-8") as handle:
        lines = [line.strip() for line in handle if line.strip()]
    return lines[:limit] if limit else lines


async def warm_one(bot: Bot, query: str, dry: bool) -> str:
    """Один запрос. Возвращает исход словом — для сводки."""
    candidate = await asyncio.to_thread(find_track, query)
    if candidate is None:
        return "не найдено"

    async with session_factory() as session:
        existing = await find_existing_track(
            session, None, candidate.title, candidate.artist or "", candidate.duration or 0
        )
        if existing is not None:
            return "уже в базе"

    if dry:
        return f"добавили бы: {candidate.artist} — {candidate.title}"

    if not enough_free_disk():
        raise SystemExit(f"Мало места на диске ({free_mb()} МБ) — прогрев остановлен")

    audio = await asyncio.to_thread(download_candidate, candidate)
    if audio is None:
        return "не скачалось"

    async with session_factory() as session:
        track, created = await import_via_telegram_mint(
            session,
            bot,
            title=candidate.title,
            artist=(audio.uploader or candidate.artist or "").strip() or "Неизвестный",
            duration=audio.duration or candidate.duration or 0,
            file_format=audio.file_format,
            data=audio.data,
            fingerprint=None,
            archive_chat_id=settings.effective_archive_chat_id,
            cover=fetch_thumbnail(audio.thumbnail_url or candidate.cover_url or ""),
            cover_url=audio.thumbnail_url or candidate.cover_url or None,
            album=audio.album or None,
            thumbnail=fetch_telegram_thumbnail(audio.thumbnail_url or candidate.cover_url or ""),
        )
    return f"заминчен #{track.id}" if created else "уже в базе"


async def run(queries: list[str], dry: bool, delay: float) -> None:
    bot = Bot(token=settings.bot_token)
    counters: dict[str, int] = {}
    started = time.perf_counter()
    try:
        for number, query in enumerate(queries, 1):
            try:
                outcome = await warm_one(bot, query, dry)
            except SystemExit:
                raise
            except Exception as exc:  # noqa: BLE001 — один запрос не должен рушить прогон
                logger.warning("«%s» — ошибка: %s", query, exc)
                outcome = "ошибка"
            key = outcome.split(":")[0].split("#")[0].strip()
            counters[key] = counters.get(key, 0) + 1
            logger.info("[%s/%s] «%s» — %s", number, len(queries), query, outcome)
            if not dry and number < len(queries):
                await asyncio.sleep(delay)
    finally:
        await bot.session.close()

    spent = time.perf_counter() - started
    logger.info("Готово за %.0f сек: %s", spent, ", ".join(f"{k} — {v}" for k, v in counters.items()))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Прогрев каталога: заранее минтит треки в архивный канал.",
        epilog=(
            "Потолок считайте по базе, а не по аудио: аудио хранит Telegram, "
            "а база растёт на ~9 КБ на трек. 100 тысяч треков ≈ 900 МБ, "
            "миллион ≈ 9 ГБ. Плюс темп: Telegram не даст лить быстрее "
            "~15 треков в минуту, то есть миллион это больше месяца непрерывно."
        ),
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--popular", type=int, metavar="N", help="N самых частых запросов людей")
    source.add_argument("--file", metavar="ПУТЬ", help="файл со списком запросов, по одному на строку")
    parser.add_argument("--limit", type=int, default=0, help="ограничить число запросов из файла")
    parser.add_argument("--delay", type=float, default=DELAY_SECONDS, help="пауза между треками, сек")
    parser.add_argument("--dry", action="store_true", help="только показать, ничего не качать")
    args = parser.parse_args()

    queries = (
        asyncio.run(popular_queries(args.popular))
        if args.popular
        else read_queries(args.file, args.limit)
    )
    if not queries:
        raise SystemExit("Список запросов пуст")
    logger.info("Запросов к прогреву: %s%s", len(queries), " (пробный прогон)" if args.dry else "")
    asyncio.run(run(queries, args.dry, args.delay))


if __name__ == "__main__":
    main()

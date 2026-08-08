"""Парсер минусов с YouTube-канала.

Канал минусов подписывает видео однообразно («МИНУС - Артист – Название
(Instrumental) #music»), поэтому фильтр по маркерам внутри такого канала не
нужен — берём всё подряд, но название чистим до «Исполнитель — Название»,
иначе поиск его не найдёт (см. services/minus_title.py).

    python -m app.cli.import_minuses --channel https://www.youtube.com/@MinusZvyaaga --dry
    python -m app.cli.import_minuses --channel https://www.youtube.com/@MinusZvyaaga --limit 50

Идемпотентен: уже залитый минус пропускается, прогон можно прерывать.
⚠️ Смешанный канал (минусы вперемешку с обычными видео) — ключ `--only-marked`:
тогда берём только то, где в названии есть «минус» или «instrumental».
"""
import argparse
import asyncio
import logging
import time

from aiogram import Bot

from app.config import settings
from app.db.base import session_factory
from app.services.catalog_import import (
    find_existing_instrumental,
    import_instrumental_via_telegram_mint,
)
from app.services.disk import enough_free_disk, free_mb
from app.services.minus_title import looks_like_minus, parse_minus_title
from app.services.youtube.downloader import download_audio

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger("minuses")

# Тот же темп, что у прогрева: Telegram не даст боту лить в чат быстрее
DELAY_SECONDS = 4.0


def list_channel_videos(channel_url: str, limit: int) -> list[tuple[str, str]]:
    """[(video_id, название)] с канала. extract_flat — без захода в каждое видео."""
    import yt_dlp

    from app.services.youtube.downloader import _base_opts

    url = channel_url.rstrip("/")
    if not url.endswith("/videos"):
        url = f"{url}/videos"
    opts = dict(_base_opts())
    opts.update({"extract_flat": True, "quiet": True, "playlistend": limit or None})
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    entries = info.get("entries") or []
    return [(item.get("id"), item.get("title") or "") for item in entries if item.get("id")]


async def import_one(bot: Bot, video_id: str, raw_title: str, dry: bool) -> str:
    artist, title = parse_minus_title(raw_title)

    async with session_factory() as session:
        existing = await find_existing_instrumental(session, None, title, artist, 0)
        if existing is not None:
            return "уже в базе"

    if dry:
        return f"добавили бы: {artist} — {title}"

    if not enough_free_disk():
        raise SystemExit(f"Мало места на диске ({free_mb()} МБ) — импорт остановлен")

    audio = await asyncio.to_thread(download_audio, video_id, True)
    if audio is None:
        return "не скачалось"

    async with session_factory() as session:
        instrumental, created = await import_instrumental_via_telegram_mint(
            session,
            bot,
            title=title,
            artist=artist,
            duration=audio.duration,
            file_format=audio.file_format,
            data=audio.data,
            fingerprint=None,
            archive_chat_id=settings.effective_archive_chat_id,
            source=f"https://www.youtube.com/watch?v={video_id}",
        )
    return f"заминчен #{instrumental.id}" if created else "уже в базе"


async def run(videos: list[tuple[str, str]], dry: bool, delay: float, only_marked: bool) -> None:
    bot = Bot(token=settings.bot_token)
    counters: dict[str, int] = {}
    started = time.perf_counter()
    try:
        for number, (video_id, raw_title) in enumerate(videos, 1):
            if only_marked and not looks_like_minus(raw_title):
                counters["не минус"] = counters.get("не минус", 0) + 1
                continue
            try:
                outcome = await import_one(bot, video_id, raw_title, dry)
            except SystemExit:
                raise
            except Exception as exc:  # noqa: BLE001 — одно видео не рушит прогон
                logger.warning("«%s» — ошибка: %s", raw_title[:50], exc)
                outcome = "ошибка"
            key = outcome.split(":")[0].split("#")[0].strip()
            counters[key] = counters.get(key, 0) + 1
            logger.info("[%s/%s] %s — %s", number, len(videos), raw_title[:55], outcome)
            if not dry and number < len(videos):
                await asyncio.sleep(delay)
    finally:
        await bot.session.close()

    spent = time.perf_counter() - started
    logger.info("Готово за %.0f сек: %s", spent, ", ".join(f"{k} — {v}" for k, v in counters.items()))


def main() -> None:
    parser = argparse.ArgumentParser(description="Импорт минусов с YouTube-канала.")
    parser.add_argument("--channel", required=True, help="ссылка на канал")
    parser.add_argument("--limit", type=int, default=0, help="сколько видео взять (0 — все)")
    parser.add_argument("--delay", type=float, default=DELAY_SECONDS, help="пауза между минусами")
    parser.add_argument("--dry", action="store_true", help="только показать, ничего не качать")
    parser.add_argument(
        "--only-marked",
        action="store_true",
        help="брать только видео с «минус»/«instrumental» в названии (для смешанных каналов)",
    )
    args = parser.parse_args()

    videos = list_channel_videos(args.channel, args.limit)
    if not videos:
        raise SystemExit("Канал пуст или не читается")
    logger.info("Видео к разбору: %s%s", len(videos), " (пробный прогон)" if args.dry else "")
    asyncio.run(run(videos, args.dry, args.delay, args.only_marked))


if __name__ == "__main__":
    main()

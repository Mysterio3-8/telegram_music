"""Перенос плейлиста из чужого сервиса в библиотеку пользователя.

По каждой паре «исполнитель — название»:
1) ищем в общей базе (совпало — мгновенно кладём в библиотеку, ничего не качаем);
2) не нашли — берём первый результат поиска YouTube и импортируем как обычную
   пользовательскую загрузку (тот же путь, что ссылка от юзера).
"""
import asyncio
import logging
import random
from dataclasses import dataclass, field

from aiogram import Bot
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import Track
from app.services.library import add_to_library
from app.services.playlist_transfer.parsers import TransferItem
from app.services.users import get_user_by_telegram_id
from app.services.youtube.downloader import search_first_video
from app.services.youtube.user_import import UserImportRejected, process_user_import

logger = logging.getLogger(__name__)


@dataclass
class TransferReport:
    total: int = 0
    matched: int = 0  # нашлись в нашей базе
    downloaded: int = 0  # догрузили из открытых источников
    failed: int = 0
    failed_examples: list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"Треков в плейлисте: {self.total}",
            f"✅ Уже были в базе: {self.matched}",
            f"⬇️ Загружено: {self.downloaded}",
        ]
        if self.failed:
            lines.append(f"❌ Не нашлось: {self.failed}")
            if self.failed_examples:
                lines.append("   " + "; ".join(self.failed_examples[:5]))
        lines.append(f"\nВсего в вашей библиотеке новых: {self.matched + self.downloaded}")
        return "\n".join(lines)


# Потолок одного переноса (решение владельца). Перенос идёт последовательно с
# паузой 5–60 сек между скачиваниями, так что 1000 треков — это до полусуток.
TRANSFER_MAX_ITEMS = 1000

# Один активный перенос на человека: без замка десять отправок подряд ставили
# десять многочасовых задач, и очередь стояла у всех.
_LOCK_PREFIX = "transfer:active:"
_LOCK_TTL_SECONDS = 24 * 3600


def _redis_sync():
    if not settings.redis_url:
        return None
    try:
        import redis

        return redis.from_url(settings.redis_url)
    except Exception:  # noqa: BLE001 — замок опционален, как и кэш поиска
        logger.warning("Перенос: Redis недоступен, замок не ставится", exc_info=True)
        return None


def acquire_transfer_lock(telegram_id: int) -> bool:
    """True — можно начинать. Redis недоступен → не блокируем: перенос важнее замка."""
    client = _redis_sync()
    if client is None:
        return True
    try:
        return bool(
            client.set(f"{_LOCK_PREFIX}{telegram_id}", "1", nx=True, ex=_LOCK_TTL_SECONDS)
        )
    except Exception:  # noqa: BLE001
        logger.warning("Перенос: не удалось поставить замок", exc_info=True)
        return True


def release_transfer_lock(telegram_id: int) -> None:
    client = _redis_sync()
    if client is None:
        return
    try:
        client.delete(f"{_LOCK_PREFIX}{telegram_id}")
    except Exception:  # noqa: BLE001 — истечёт сам по TTL
        logger.warning("Перенос: не удалось снять замок", exc_info=True)


async def find_in_catalog(session: AsyncSession, item: TransferItem) -> Track | None:
    """Точное совпадение исполнителя и названия без учёта регистра и транслита.

    ⚠️ По search_index, а не lower() в запросе: SQLite lower() не понижает
    кириллицу, и «Макан — Назови» из Яндекса никогда не находился в базе, где он
    записан «МАКАН — Назови», — перенос качал заново уже имеющийся трек. Прежнее
    сравнение осталось фолбэком для строк без индекса.
    """
    from app.services.search import find_track_by_metadata

    found = await find_track_by_metadata(session, item.artist, item.title)
    if found is not None:
        return found
    return await session.scalar(
        select(Track)
        .where(
            func.lower(func.trim(Track.title)) == item.title.strip().lower(),
            func.lower(func.trim(Track.artist)) == item.artist.strip().lower(),
        )
        .limit(1)
    )


async def transfer_playlist(
    session: AsyncSession,
    bot: Bot,
    items: list[TransferItem],
    telegram_id: int,
    *,
    download_missing: bool = True,
) -> TransferReport:
    user = await get_user_by_telegram_id(session, telegram_id)
    if user is None:
        raise UserImportRejected("Пользователь не найден — отправьте /start")

    report = TransferReport(total=len(items))
    for index, item in enumerate(items):
        existing = await find_in_catalog(session, item)
        if existing is not None:
            await add_to_library(session, user.id, existing.id)
            report.matched += 1
            continue

        if not download_missing:
            report.failed += 1
            report.failed_examples.append(item.query())
            continue

        if index:
            # Пауза между сетевыми загрузками — как в SoundCloud-импорте
            await asyncio.sleep(
                random.uniform(settings.soundcloud_min_delay, settings.soundcloud_max_delay)
            )
        try:
            entry = await asyncio.to_thread(search_first_video, item.query())
            if entry is None:
                raise RuntimeError("поиск ничего не вернул")
            await process_user_import(session, bot, entry.video_id, telegram_id)
            report.downloaded += 1
        except Exception as exc:  # noqa: BLE001 — один трек не должен рушить перенос
            report.failed += 1
            report.failed_examples.append(item.query())
            logger.info("Перенос: не удалось «%s» (%s)", item.query(), exc)

    logger.info("Перенос плейлиста user=%s: %s", telegram_id, report.summary().replace("\n", "; "))
    return report

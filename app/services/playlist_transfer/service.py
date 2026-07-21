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


async def find_in_catalog(session: AsyncSession, item: TransferItem) -> Track | None:
    """Точное совпадение исполнителя и названия без учёта регистра и пробелов."""
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

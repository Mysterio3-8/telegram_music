"""Импорт треков с SoundCloud (админ, по ссылке): трек/профиль/сет → общая база.

Каждый трек скачивается yt-dlp, проходит музыкальные границы длительности,
минтится через бота (tg_file_id) и попадает в tracks с дедупом — повторный скан
источника забирает только новое.
"""
import asyncio
import logging
import random
from dataclasses import dataclass

from aiogram import Bot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import SoundcloudImported
from app.services.catalog_import import import_via_telegram_mint
from app.services.fingerprint import compute_fingerprint_from_bytes
from app.services.soundcloud import download_soundcloud_audio, list_soundcloud_entries
from app.services.title_parser import parse_title
from app.services.youtube.user_import import duration_error

logger = logging.getLogger(__name__)

# Пауза между скачиваниями (сек): рандомизированная, чтобы не выглядеть как бот
# и не словить бан по частоте запросов к SoundCloud.
_MIN_DELAY = 2.0
_MAX_DELAY = 5.0


async def _already_seen(session: AsyncSession, url: str) -> bool:
    return await session.scalar(
        select(SoundcloudImported.id).where(SoundcloudImported.url == url).limit(1)
    ) is not None


async def _mark_seen(session: AsyncSession, url: str) -> None:
    session.add(SoundcloudImported(url=url))
    await session.commit()


@dataclass
class SoundcloudReport:
    found: int = 0
    imported: int = 0
    duplicates: int = 0
    rejected: int = 0
    failed: int = 0
    skipped_known: int = 0  # уже обрабатывались ранее — не качали повторно

    def summary(self) -> str:
        lines = [f"Найдено ссылок: {self.found}", f"✅ Импортировано новых: {self.imported}"]
        if self.skipped_known:
            lines.append(f"⏩ Уже обработаны ранее (пропущены): {self.skipped_known}")
        if self.duplicates:
            lines.append(f"↩️ Дубликаты в базе: {self.duplicates}")
        if self.rejected:
            lines.append(f"⏭ Не музыка: {self.rejected}")
        if self.failed:
            lines.append(f"❌ Ошибок скачивания: {self.failed}")
        return "\n".join(lines)


async def import_soundcloud_tracks(
    session: AsyncSession, bot: Bot, url: str
) -> SoundcloudReport:
    report = SoundcloudReport()
    all_entries = list_soundcloud_entries(url)
    if settings.playlist_import_limit:
        all_entries = all_entries[: settings.playlist_import_limit]
    report.found = len(all_entries)

    # Инкрементально: уже обработанные ссылки пропускаем без скачивания (анти-бан)
    entries = [e for e in all_entries if not await _already_seen(session, e.url)]
    report.skipped_known = report.found - len(entries)

    for index, entry in enumerate(entries):
        if index:
            await asyncio.sleep(random.uniform(_MIN_DELAY, _MAX_DELAY))
        try:
            result = download_soundcloud_audio(entry.url)
        except Exception:  # noqa: BLE001 — один битый трек не роняет пачку (ошибку не помечаем — повторим)
            logger.exception("SoundCloud: не скачался %s", entry.url)
            report.failed += 1
            continue
        if result is None:
            report.failed += 1
            continue
        audio, uploader = result

        if duration_error(audio.duration) or len(audio.data) > settings.max_file_size_mb * 1024 * 1024:
            report.rejected += 1
            await _mark_seen(session, entry.url)  # не музыка — больше не качать
            continue

        artist, title = parse_title(audio.video_title, uploader or "Unknown")
        fingerprint = compute_fingerprint_from_bytes(audio.data, suffix=f".{audio.file_format}")
        _track, created = await import_via_telegram_mint(
            session,
            bot,
            title=title,
            artist=artist,
            duration=audio.duration,
            file_format=audio.file_format,
            data=audio.data,
            fingerprint=fingerprint,
            archive_chat_id=settings.effective_archive_chat_id,
        )
        if created:
            report.imported += 1
        else:
            report.duplicates += 1
        await _mark_seen(session, entry.url)  # успешно обработана — в следующий скан не качаем

    logger.info("SoundCloud-импорт %s: %s", url, report.summary().replace("\n", "; "))
    return report

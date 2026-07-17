"""Импорт треков с SoundCloud (админ, по ссылке): трек/профиль/сет → общая база.

Каждый трек скачивается yt-dlp, проходит музыкальные границы длительности,
минтится через бота (tg_file_id) и попадает в tracks с дедупом — повторный скан
источника забирает только новое.
"""
import logging
from dataclasses import dataclass

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.services.catalog_import import import_via_telegram_mint
from app.services.fingerprint import compute_fingerprint_from_bytes
from app.services.soundcloud import download_soundcloud_audio, list_soundcloud_entries
from app.services.title_parser import parse_title
from app.services.youtube.user_import import duration_error

logger = logging.getLogger(__name__)


@dataclass
class SoundcloudReport:
    found: int = 0
    imported: int = 0
    duplicates: int = 0
    rejected: int = 0
    failed: int = 0

    def summary(self) -> str:
        lines = [f"Найдено треков: {self.found}", f"✅ Импортировано: {self.imported}"]
        if self.duplicates:
            lines.append(f"↩️ Уже были в базе: {self.duplicates}")
        if self.rejected:
            lines.append(f"⏭ Не музыка (короче/длиннее лимитов): {self.rejected}")
        if self.failed:
            lines.append(f"❌ Ошибок скачивания: {self.failed}")
        return "\n".join(lines)


async def import_soundcloud_tracks(
    session: AsyncSession, bot: Bot, url: str
) -> SoundcloudReport:
    report = SoundcloudReport()
    entries = list_soundcloud_entries(url)[: settings.playlist_import_limit]
    report.found = len(entries)

    for entry in entries:
        try:
            result = download_soundcloud_audio(entry.url)
        except Exception:  # noqa: BLE001 — один битый трек не роняет пачку
            logger.exception("SoundCloud: не скачался %s", entry.url)
            report.failed += 1
            continue
        if result is None:
            report.failed += 1
            continue
        audio, uploader = result

        if duration_error(audio.duration):
            report.rejected += 1
            continue
        if len(audio.data) > settings.max_file_size_mb * 1024 * 1024:
            report.rejected += 1
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

    logger.info("SoundCloud-импорт %s: %s", url, report.summary().replace("\n", "; "))
    return report

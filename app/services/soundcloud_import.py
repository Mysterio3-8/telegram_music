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
from app.services.youtube.downloader import fetch_thumbnail
from app.services.title_parser import parse_title
from app.services.youtube.user_import import duration_error

logger = logging.getLogger(__name__)

# Сообщения yt-dlp, означающие «трек никогда не скачается» (не сеть легла, а
# сам трек недоступен — Go+/приватный/удалённый). Такие метим как обработанные,
# иначе каждый день будем заново долбить SoundCloud по заведомо мёртвой ссылке.
_PERMANENT_FAILURE_MARKERS = ("drm protected", "track unavailable", "this track is private")


def _is_permanent_failure(error: Exception) -> bool:
    text = str(error).lower()
    return any(marker in text for marker in _PERMANENT_FAILURE_MARKERS)


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

    # Полная анти-бан-пауза нужна после реального скачивания; отказ DRM-трека —
    # дешёвый запрос метаданных, после него хватает короткой (иначе профиль
    # мейджора из сотен Go+-треков «сканируется» сутками впустую)
    heavy_last = False
    for index, entry in enumerate(entries):
        if index:
            if heavy_last:
                await asyncio.sleep(
                    random.uniform(settings.soundcloud_min_delay, settings.soundcloud_max_delay)
                )
            else:
                await asyncio.sleep(random.uniform(1.0, 3.0))
        heavy_last = True
        try:
            result = download_soundcloud_audio(entry.url)
        except Exception as exc:  # noqa: BLE001 — один битый трек не роняет пачку
            report.failed += 1
            if _is_permanent_failure(exc):
                # Go+/приватный/удалённый — не сеть, а сам трек. Больше не пытаемся.
                logger.info("SoundCloud: %s недоступен навсегда (%s)", entry.url, exc)
                await _mark_seen(session, entry.url)
                heavy_last = False
            else:
                logger.exception("SoundCloud: не скачался %s", entry.url)
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
            cover=fetch_thumbnail(audio.thumbnail_url),
            cover_url=audio.thumbnail_url or None,
            album=audio.album or None,
        )
        if created:
            report.imported += 1
        else:
            report.duplicates += 1
        await _mark_seen(session, entry.url)  # успешно обработана — в следующий скан не качаем

    logger.info("SoundCloud-импорт %s: %s", url, report.summary().replace("\n", "; "))
    return report


async def process_user_soundcloud_import(
    session: AsyncSession, bot: Bot, url: str, telegram_id: int
) -> tuple:
    """Одиночный трек SoundCloud от пользователя: скачать, завести в общую базу,
    добавить в библиотеку пользователя. Возвращает (трек, создан_ли).
    Зеркало youtube.user_import.process_user_import для SoundCloud."""
    from app.db.models import Upload
    from app.services.library import add_to_library
    from app.services.users import get_user_by_telegram_id
    from app.services.youtube.user_import import UserImportRejected

    user = await get_user_by_telegram_id(session, telegram_id)
    if user is None:
        raise UserImportRejected("Пользователь не найден — отправьте /start")

    result = download_soundcloud_audio(url)
    if result is None:
        raise RuntimeError(f"yt-dlp не вернул аудио для {url}")
    audio, uploader = result

    error = duration_error(audio.duration)
    if error:
        raise UserImportRejected(error)
    if len(audio.data) > settings.max_file_size_mb * 1024 * 1024:
        raise UserImportRejected(f"Файл больше {settings.max_file_size_mb} МБ.")

    artist, title = parse_title(audio.video_title, uploader or "Unknown")
    fingerprint = compute_fingerprint_from_bytes(audio.data, suffix=f".{audio.file_format}")
    track, created = await import_via_telegram_mint(
        session,
        bot,
        title=title,
        artist=artist,
        duration=audio.duration,
        file_format=audio.file_format,
        data=audio.data,
        fingerprint=fingerprint,
        archive_chat_id=settings.effective_archive_chat_id,
        cover=fetch_thumbnail(audio.thumbnail_url),
        cover_url=audio.thumbnail_url or None,
        album=audio.album or None,
    )
    if created:
        session.add(Upload(user_id=user.id, track_id=track.id))
        await session.commit()
    await add_to_library(session, user.id, track.id)
    logger.info("SoundCloud user-импорт %s user=%s → track=%s", url, telegram_id, track.id)
    return track, created

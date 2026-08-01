"""Сторож диска: чистит лишнее заранее и зовёт админа, если не справился.

Почему отдельно от disk.py: там пассивная проверка «можно ли писать», здесь
активное освобождение места. LRU-кэш аудио вытесняет себя только в момент
записи — если диск набивают системные логи или бэкапы БД, вытеснять его некому,
и переполнение приходит без единого предупреждения (инциденты 2026-07-26/27:
диск 100% → Redis не смог сделать снимок → бот перестал отвечать).

Порядок чистки — от наименее ценного к более ценному:
1. кэш аудио (чистая производная, восстанавливается скачиванием заново);
2. лишние бэкапы БД, кроме самых свежих backup_keep_low_disk.

База, архивные копии треков и чужие каталоги на сервере не трогаются никогда.
"""
import logging
from dataclasses import dataclass
from pathlib import Path

from app.config import settings
from app.services.disk import free_mb

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReclaimReport:
    free_before_mb: int
    free_after_mb: int
    removed_cache_files: int
    removed_backups: int

    @property
    def freed_mb(self) -> int:
        return self.free_after_mb - self.free_before_mb

    @property
    def did_anything(self) -> bool:
        return bool(self.removed_cache_files or self.removed_backups)


def _oldest_first(root: Path) -> list[Path]:
    """Файлы каталога от самых давно нетронутых к свежим. Нет каталога → пусто."""
    try:
        files = [f for f in root.iterdir() if f.is_file()]
    except OSError:
        return []
    return sorted(files, key=lambda f: f.stat().st_mtime)


def _delete_until_free(files: list[Path], target_mb: int) -> int:
    """Удаляет файлы по порядку, пока свободного места не станет target_mb."""
    removed = 0
    for file in files:
        if free_mb() >= target_mb:
            break
        try:
            file.unlink()
        except OSError:
            continue
        removed += 1
    return removed


def reclaim_disk(target_free_mb: int | None = None) -> ReclaimReport:
    """Освобождает место, пока свободного не станет target_free_mb (или сколько выйдет)."""
    target = target_free_mb if target_free_mb is not None else settings.disk_reclaim_free_mb
    before = free_mb()
    if before >= target:
        return ReclaimReport(before, before, 0, 0)

    logger.warning("Мало места: %s МБ при пороге %s МБ — чищу", before, target)
    removed_cache = _delete_until_free(_oldest_first(Path(settings.audio_cache_dir)), target)

    removed_backups = 0
    if free_mb() < target:
        backups = sorted(
            Path(settings.backup_dir).glob("db-*.*"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        # Самые свежие backup_keep_low_disk копий неприкосновенны: освобождать
        # место ценой полного отсутствия бэкапа — плохой размен.
        removed_backups = _delete_until_free(
            list(reversed(backups[settings.backup_keep_low_disk :])), target
        )

    after = free_mb()
    report = ReclaimReport(before, after, removed_cache, removed_backups)
    logger.info(
        "Чистка диска: было %s МБ, стало %s МБ (кэш: %s файлов, бэкапы: %s)",
        before,
        after,
        removed_cache,
        removed_backups,
    )
    return report


def alert_text(report: ReclaimReport) -> str | None:
    """Текст предупреждения админу или None, если места достаточно."""
    if report.free_after_mb >= settings.disk_alert_free_mb:
        return None
    lines = [
        "⚠️ Мало места на диске",
        "",
        f"Свободно: {report.free_after_mb} МБ (порог {settings.disk_alert_free_mb} МБ)",
    ]
    if report.did_anything:
        lines.append(
            f"Автоочистка освободила {report.freed_mb} МБ "
            f"(кэш: {report.removed_cache_files} файлов, бэкапы: {report.removed_backups})"
        )
    else:
        lines.append("Чистить нечего — место заняли база, логи или архив треков.")
    lines += ["", "Проверить: ssh news-rewriter-vps 'du -xh --max-depth=2 / | sort -rh | head -20'"]
    return "\n".join(lines)

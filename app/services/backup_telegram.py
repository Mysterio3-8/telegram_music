"""Копия бэкапа вне сервера через Telegram (16.09): зашифрованный снимок — владельцу.

Рядом живёт backup_offsite.py (выгрузка в S3) — она включается только с ключами
хранилища, а их нет. Этот путь не требует ничего, кроме бота.

Зачем: снимки лежали на том же диске, что и база (`backups/`). Умирает диск или
сервер — пропадают и база, и оба снимка. Проверка 16.09 показала, что сам снимок
годный (целостность, схема, приложение поверх копии), — не хватало только места,
которое переживёт сервер.

Почему так:
- **Шифруем всегда.** В базе Telegram-id людей, платежи и донаты. Без пароля файл
  из переписки бесполезен. Нет `BACKUP_PASSWORD` — отправка отказывается работать,
  а не шлёт открытый файл «пока пароля нет».
- **openssl, а не библиотека.** Он есть на сервере и в Git Bash на Windows, то есть
  расшифровать копию можно там, где сервера уже нет, без нашего кода:
  `openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -in X.enc -out X.gz -pass pass:ПАРОЛЬ`
  и затем `gzip -d X.gz`. Инструкция — docs/БЭКАП.md.
- **Сжатие до шифрования.** Зашифрованное не сжимается; SQLite ужимается в разы.
- Потолок Bot API на документ — 50 МБ; больше не отправляем и говорим об этом.
"""
from __future__ import annotations

import gzip
import logging
import os
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

TELEGRAM_DOCUMENT_LIMIT = 49 * 1024 * 1024
_OPENSSL_ARGS = ["-aes-256-cbc", "-pbkdf2", "-iter", "200000", "-salt"]


class OffsiteBackupError(RuntimeError):
    pass


def latest_backup(backup_dir: str | Path) -> Path | None:
    files = sorted(Path(backup_dir).glob("db-*.*"), key=lambda p: p.stat().st_mtime, reverse=True)
    files = [f for f in files if not f.name.endswith(".enc")]
    return files[0] if files else None


def _openssl(args: list[str], password: str) -> None:
    binary = shutil.which("openssl")
    if binary is None:
        raise OffsiteBackupError("openssl не найден — шифровать нечем")
    # Пароль через окружение, а не аргументом: аргументы видны в `ps` всем на машине
    env = {**os.environ, "BACKUP_PASS": password}
    result = subprocess.run([binary, *args, "-pass", "env:BACKUP_PASS"], env=env, capture_output=True, timeout=300)
    if result.returncode != 0:
        raise OffsiteBackupError(f"openssl: {result.stderr.decode(errors='replace').strip()[:200]}")


def encrypt_backup(source: Path, target: Path, password: str) -> Path:
    """gzip → AES-256. Промежуточный .gz удаляется в любом случае."""
    if not password:
        raise OffsiteBackupError("не задан BACKUP_PASSWORD — открытую базу не отправляем")
    packed = target.with_suffix(target.suffix + ".gz.tmp")
    try:
        with source.open("rb") as raw, gzip.open(packed, "wb", compresslevel=6) as out:
            shutil.copyfileobj(raw, out, length=1024 * 1024)
        _openssl(["enc", *_OPENSSL_ARGS, "-in", str(packed), "-out", str(target)], password)
    finally:
        packed.unlink(missing_ok=True)
    return target


def decrypt_backup(source: Path, target: Path, password: str) -> Path:
    """Обратная операция — для проверки и для восстановления."""
    packed = target.with_suffix(target.suffix + ".gz.tmp")
    try:
        _openssl(["enc", "-d", *_OPENSSL_ARGS[:-1], "-in", str(source), "-out", str(packed)], password)
        with gzip.open(packed, "rb") as src, target.open("wb") as out:
            shutil.copyfileobj(src, out, length=1024 * 1024)
    finally:
        packed.unlink(missing_ok=True)
    return target


async def send_document(chat_id: int, path: Path, caption: str) -> bool:
    import aiohttp

    from app.config import settings

    data = aiohttp.FormData()
    data.add_field("chat_id", str(chat_id))
    data.add_field("caption", caption)
    with path.open("rb") as handle:
        data.add_field("document", handle, filename=path.name, content_type="application/octet-stream")
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=300)) as http:
                async with http.post(
                    f"https://api.telegram.org/bot{settings.bot_token}/sendDocument", data=data
                ) as response:
                    if response.status != 200:
                        logger.error("Бэкап: sendDocument %s", response.status)
                        return False
                    return True
        except aiohttp.ClientError:
            logger.warning("Бэкап: Telegram недоступен", exc_info=True)
            return False


async def send_to_owner(path: Path) -> str:
    """Зашифровать снимок и отправить владельцу. Возвращает строку-итог для журнала.

    Никогда не бросает: копия в Telegram — второй рубеж, её сбой не должен ронять
    ежедневный таймер, где сам снимок уже сделан.
    """
    import tempfile
    from datetime import date

    from app.config import settings

    if not settings.backup_password:
        return "Копия в Telegram выключена: не задан BACKUP_PASSWORD"
    chat_id = settings.health_alert_id
    if chat_id is None:
        return "Копия в Telegram выключена: некому отправлять (нет ADMIN_IDS)"
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / f"infinity-db-{date.today().isoformat()}.sqlite.gz.enc"
        try:
            encrypt_backup(path, target, settings.backup_password)
        except OffsiteBackupError as error:
            logger.warning("Бэкап: шифрование не удалось: %s", error)
            return f"Копия в Telegram не отправлена: {error}"
        size = target.stat().st_size
        if size > TELEGRAM_DOCUMENT_LIMIT:
            return f"Копия в Telegram не отправлена: {size // 1024 // 1024} МБ больше лимита Bot API"
        caption = (
            f"🗄 Бэкап базы {date.today():%d.%m.%Y} · {max(1, size // 1024 // 1024)} МБ, зашифрован.\n"
            "Как восстановить — docs/БЭКАП.md. Пароль в сообщении не присылаем."
        )
        if not await send_document(chat_id, target, caption):
            return "Копия в Telegram не отправлена: Telegram не принял файл (подробности в журнале)"
    return f"Копия в Telegram отправлена ({size // 1024} КБ)"

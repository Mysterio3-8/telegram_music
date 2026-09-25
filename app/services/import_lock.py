"""Один импорт на одну ссылку источника — на все процессы сразу (24.09).

🔴 Находка сверки данных прода 24.09: трек «BONES — Dashboard» заведён ДВАЖДЫ
с одной и той же ссылкой, записи 33007 и 33008 с разницей в секунду, обе
заминчены. Проверка «уже есть по source_url» стоит в начале импорта, а вставка —
после скачивания, секунды спустя. Два потока (предзагрузка выдачи, нажатие
человека, прогрев, оживление трека в API) проходили проверку одновременно и оба
качали.

Замок в Redis, потому что участники живут в РАЗНЫХ процессах: воркер поиска,
основной воркер, CLI прогрева, API. Второй пришедший не качает, а ждёт первого и
забирает готовый трек.

Redis недоступен → замка нет, импорт работает как раньше (редкий дубль лучше,
чем отказ выдать трек).
"""
from __future__ import annotations

import hashlib
import logging

logger = logging.getLogger(__name__)

LOCK_TTL_SECONDS = 240  # дольше самого медленного импорта: yt-dlp + ffmpeg + минт
_PREFIX = "import:url:"


def _key(url: str) -> str:
    return _PREFIX + hashlib.sha1((url or "").encode()).hexdigest()


def _redis():
    from app.services.prefetch import _redis as shared

    return shared()


def acquire(url: str) -> bool:
    """True — импорт наш. False — ссылку уже качает кто-то другой."""
    client = _redis()
    if client is None:
        return True
    try:
        return bool(client.set(_key(url), "1", nx=True, ex=LOCK_TTL_SECONDS))
    except Exception:  # noqa: BLE001 — Redis лёг посреди работы: не мешаем импорту
        logger.warning("Замок импорта недоступен", exc_info=True)
        return True


def release(url: str) -> None:
    client = _redis()
    if client is None:
        return
    try:
        client.delete(_key(url))
    except Exception:  # noqa: BLE001
        logger.warning("Замок импорта не снят — истечёт сам", exc_info=True)


def is_locked(url: str) -> bool:
    client = _redis()
    if client is None:
        return False
    try:
        return bool(client.exists(_key(url)))
    except Exception:  # noqa: BLE001
        return False

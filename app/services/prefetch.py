"""Предзагрузка верха выдачи живого поиска (19.09, запрос владельца).

Эталон владельца — @RuMediaBot: нажал номер трека, и аудио в чате через секунду.
У нас трек, которого ещё нет в базе, качается и минтится ПОСЛЕ нажатия — это
секунды ожидания. Лечение — начать качать заранее, пока человек читает список:
к моменту нажатия трек уже в базе и уходит мгновенно по file_id.

Берём только первые `PREFETCH_TOP` (решение владельца — 3): туда приходится
почти каждое нажатие, а вся страница на сервере с одним ядром — это очередь
скачиваний на каждый поиск.

Два замка в Redis:
- общий слот: одновременно идёт ОДНА предзагрузка на весь бот. У воркера два
  потока, и второй обязан оставаться свободным для того, что человек нажал сам.
  Слот занят — предзагрузка просто пропускается: это ускорение, а не обязанность;
- метка на ссылку: пока кандидат качается заранее, нажатие на него не ставит
  второе скачивание, а дожидается первого (`wait_for_prefetched` в боте).

Redis недоступен → предзагрузки нет вовсе (без общего слота она заняла бы оба
потока), а нажатия работают как раньше.
"""
from __future__ import annotations

import hashlib
import logging

logger = logging.getLogger(__name__)

PREFETCH_TOP = 3
_SLOT_KEY = "prefetch:slot"
_URL_PREFIX = "prefetch:url:"
# С запасом больше трёх скачиваний подряд (~8 сек каждое); умерший воркер не
# должен держать слот дольше этого.
SLOT_TTL_SECONDS = 90
URL_TTL_SECONDS = 45


def _redis():
    from app.config import settings

    if not settings.redis_url:
        return None
    try:
        import redis

        return redis.from_url(settings.redis_url)
    except Exception:  # noqa: BLE001
        logger.warning("Предзагрузка: Redis недоступен", exc_info=True)
        return None


def _url_key(url: str) -> str:
    return _URL_PREFIX + hashlib.sha1(url.encode()).hexdigest()


def pick_for_prefetch(candidates: list, known_urls: set[str], top: int = PREFETCH_TOP) -> list:
    """Первые `top` кандидатов выдачи, которых ещё нет в базе.

    Считаем от верха выдачи, а не «первые три незалитых»: человек смотрит на
    первые строки, и качать седьмой трек только потому, что первые шесть уже в
    базе, — трата ядра на то, что вряд ли нажмут.
    """
    return [item for item in candidates[:top] if item.url and item.url not in known_urls]


def acquire_slot() -> bool:
    client = _redis()
    if client is None:
        return False
    try:
        return bool(client.set(_SLOT_KEY, "1", nx=True, ex=SLOT_TTL_SECONDS))
    except Exception:  # noqa: BLE001
        logger.warning("Предзагрузка: не удалось занять слот", exc_info=True)
        return False


def release_slot() -> None:
    client = _redis()
    if client is None:
        return
    try:
        client.delete(_SLOT_KEY)
    except Exception:  # noqa: BLE001 — истечёт сам
        logger.warning("Предзагрузка: не удалось освободить слот", exc_info=True)


def mark_url(url: str) -> None:
    client = _redis()
    if client is None:
        return
    try:
        client.set(_url_key(url), "1", ex=URL_TTL_SECONDS)
    except Exception:  # noqa: BLE001
        logger.warning("Предзагрузка: не удалось пометить ссылку", exc_info=True)


def unmark_url(url: str) -> None:
    client = _redis()
    if client is None:
        return
    try:
        client.delete(_url_key(url))
    except Exception:  # noqa: BLE001
        pass


def is_prefetching(url: str) -> bool:
    client = _redis()
    if client is None:
        return False
    try:
        return bool(client.exists(_url_key(url)))
    except Exception:  # noqa: BLE001
        return False

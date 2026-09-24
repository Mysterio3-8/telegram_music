"""Предзагрузка верха выдачи живого поиска (19.09, запрос владельца).

Эталон владельца — @RuMediaBot: нажал номер трека, и аудио в чате через секунду.
У нас трек, которого ещё нет в базе, качается и минтится ПОСЛЕ нажатия — это
секунды ожидания. Лечение — начать качать заранее, пока человек читает список:
к моменту нажатия трек уже в базе и уходит мгновенно по file_id.

Берём первые `PREFETCH_TOP` из выдачи. Было 3, стало 20 — вся показанная
страница: владелец 21.09 просил прогревать её целиком («выдаётся 20 треков, он
нажимает один, но минтятся и остальные 20 — только ему не присылаются»).
Сервер это выдерживает не потому, что стал мощнее, а потому что предзагрузка
уступает: она идёт по одному треку в общем слоте и бросает работу, как только в
очереди появляется нажатие живого человека (`user_waiting`).

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

PREFETCH_TOP = 20
_SLOT_KEY = "prefetch:slot"
_URL_PREFIX = "prefetch:url:"
# ⚠️ Замок должен переживать ВСЮ предзагрузку. Первая версия ставила 90 сек при
# реальной работе до 260 сек (замер прода 21.09): замок истекал на ходу, вторая
# предзагрузка занимала второй поток воркера, и нажатие человека ждало в очереди
# три минуты. Теперь с запасом плюс продление между треками.
SLOT_TTL_SECONDS = 600
URL_TTL_SECONDS = 120

# Очередь, в которой лежат нажатия людей. Пока в ней что-то есть, предзагрузка
# не имеет права занимать поток: её работа ускоряет будущее нажатие, а чужое
# нажатие уже ждёт человек.
USER_QUEUE = "youtube_user"


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


def refresh_slot() -> None:
    """Продлевает замок между треками — длинная предзагрузка не теряет его на ходу."""
    client = _redis()
    if client is None:
        return
    try:
        client.expire(_SLOT_KEY, SLOT_TTL_SECONDS)
    except Exception:  # noqa: BLE001
        pass


def user_waiting() -> bool:
    """True — в очереди есть работа от человека, предзагрузке пора уступить."""
    client = _redis()
    if client is None:
        return False
    try:
        return bool(client.llen(USER_QUEUE))
    except Exception:  # noqa: BLE001
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

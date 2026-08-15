"""Ротация прокси для массового скачивания (SoundCloud 24/7).

Список — settings.proxy_list (через запятую). Выдача по кругу: каждый запрос
уходит со следующего адреса, при ошибке вызывающая сторона просто берёт
следующий. Потокобезопасно — Celery-воркер SoundCloud работает в threads-пуле.
"""
import itertools
import threading

from app.config import settings

_lock = threading.Lock()
_cycle: "itertools.cycle[str] | None" = None
_cycle_source: tuple[str, ...] = ()


def next_proxy() -> str | None:
    """Следующий прокси по кругу; None — прокси не настроены."""
    proxies = tuple(settings.proxy_list_items)
    if not proxies:
        return None
    global _cycle, _cycle_source
    with _lock:
        if _cycle is None or _cycle_source != proxies:
            _cycle_source = proxies
            _cycle = itertools.cycle(proxies)
        return next(_cycle)


_yt_lock = threading.Lock()
_yt_offset = 0


def youtube_proxy_chain() -> list[str | None]:
    """Порядок попыток для YouTube: несколько РАЗНЫХ выходов VPN, в конце None
    (прямое соединение).

    Почему перебор, а не один прокси: отказы YouTube плавают по выходным узлам —
    замер 14.08 показал, что один и тот же трек через один выход отдаёт 403, а
    через соседний скачивается. Перебор соседей и есть лечение.

    Почему со сдвигом, а не всегда с первого: иначе весь трафик шёл бы через
    один узел, он первым получил бы репутацию бота, и остальные четыре стояли бы
    без дела до его смерти.

    Прямая попытка в конце обречена, пока YouTube блокирует IP сервера, но
    оставлена сознательно: если Xray лёг, честный отказ лучше молчания.
    """
    exits = settings.youtube_proxy_items
    if not exits:
        return [None]

    global _yt_offset
    with _yt_lock:
        start = _yt_offset % len(exits)
        _yt_offset = (_yt_offset + 1) % len(exits)

    limit = max(1, min(settings.youtube_proxy_attempts, len(exits)))
    chain: list[str | None] = [exits[(start + i) % len(exits)] for i in range(limit)]
    chain.append(None)
    return chain

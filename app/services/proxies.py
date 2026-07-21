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

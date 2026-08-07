"""Прямой поиск по API SoundCloud поверх постоянного соединения.

Зачем в обход yt-dlp: он на каждый поиск поднимает свой экстрактор и НОВОЕ
TLS-соединение, а один поиск у нас делает два-три таких вызова (оригинал запроса,
транслит, иногда YouTube). Замер: новое соединение — 8.5 сек, переиспользованное
к тому же хосту — 0.66-0.93 сек. Платим мы за рукопожатие, а не за сам поиск.

Поэтому здесь держится одно живое keep-alive соединение на процесс и переживает
все запросы. yt-dlp остаётся для СКАЧИВАНИЯ (там он незаменим) и как запасной
путь поиска, если API ответил отказом.

client_id — публичный ключ веб-плеера SoundCloud, его вытаскивают из их же JS.
Он меняется, поэтому при 401 берём заново.
"""
import http.client
import json
import logging
import re
import threading
import urllib.parse
import urllib.request

from app.services.track_lookup.ranking import Candidate

logger = logging.getLogger(__name__)

_API_HOST = "api-v2.soundcloud.com"
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"
_HEADERS = {"User-Agent": _UA, "Accept": "application/json", "Connection": "keep-alive"}
_TIMEOUT = 8
_CLIENT_ID_RE = re.compile(r'client_id[:=]"([A-Za-z0-9]{32})"')
_SCRIPT_RE = re.compile(r'src="(https://a-v2\.sndcdn\.com/assets/[^"]+\.js)"')

# Соединение и client_id общие на процесс, поэтому под замком: провайдер
# вызывается из asyncio.to_thread, то есть из нескольких потоков сразу.
_lock = threading.Lock()
_connection: http.client.HTTPSConnection | None = None
_client_id: str | None = None


def _fetch_text(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
        return response.read().decode("utf-8", "replace")


_REDIS_KEY = "soundcloud:client_id"
_CLIENT_ID_TTL = 24 * 3600


def _redis_client():
    from app.config import settings

    if not settings.redis_url:
        return None
    try:
        import redis

        return redis.from_url(settings.redis_url, decode_responses=True)
    except Exception:  # noqa: BLE001 — кэш опционален
        return None


def _cached_client_id() -> str | None:
    client = _redis_client()
    if client is None:
        return None
    try:
        return client.get(_REDIS_KEY)
    except Exception:  # noqa: BLE001
        return None


def _remember_client_id(value: str) -> None:
    """Ключ живёт в Redis сутки: добыть его — это скачать JS-бандлы SoundCloud,
    почти 20 секунд. Без общего кэша эту цену платил бы первый человек после
    каждого рестарта воркера."""
    client = _redis_client()
    if client is None:
        return
    try:
        client.set(_REDIS_KEY, value, ex=_CLIENT_ID_TTL)
    except Exception:  # noqa: BLE001
        pass


def _load_client_id() -> str | None:
    """Достаёт ключ веб-плеера из JS-бандлов SoundCloud. Их несколько, ключ
    обычно в последнем — идём с конца, чтобы не качать лишние."""
    cached = _cached_client_id()
    if cached:
        return cached
    try:
        html = _fetch_text("https://soundcloud.com/discover")
    except Exception:  # noqa: BLE001 — сеть/бан: поиск уйдёт на запасной путь
        logger.warning("SoundCloud API: страница недоступна", exc_info=True)
        return None
    for script_url in reversed(_SCRIPT_RE.findall(html)):
        try:
            found = _CLIENT_ID_RE.search(_fetch_text(script_url))
        except Exception:  # noqa: BLE001
            continue
        if found:
            _remember_client_id(found.group(1))
            return found.group(1)
    logger.warning("SoundCloud API: client_id не нашёлся в бандлах")
    return None


def refresh_client_id() -> str | None:
    """Принудительно обновляет ключ, минуя кэш (для CLI прогрева и при 401)."""
    global _client_id
    client = _redis_client()
    if client is not None:
        try:
            client.delete(_REDIS_KEY)
        except Exception:  # noqa: BLE001
            pass
    with _lock:
        _client_id = _load_client_id()
        return _client_id


def _request(path: str) -> bytes | None:
    """GET по живому соединению. Разорвалось — пересоздаём и повторяем один раз."""
    global _connection
    for attempt in (1, 2):
        try:
            if _connection is None:
                _connection = http.client.HTTPSConnection(_API_HOST, timeout=_TIMEOUT)
            _connection.request("GET", path, headers=_HEADERS)
            response = _connection.getresponse()
            body = response.read()
            if response.status == 401:
                return None  # ключ протух, обновит вызывающий
            if response.status != 200:
                logger.warning("SoundCloud API: ответ %s", response.status)
                return None
            return body
        except Exception:  # noqa: BLE001 — соединение умерло, вторая попытка со свежим
            try:
                if _connection is not None:
                    _connection.close()
            except Exception:  # noqa: BLE001
                pass
            _connection = None
            if attempt == 2:
                logger.warning("SoundCloud API: запрос не удался", exc_info=True)
                return None
    return None


def _to_candidate(item: dict) -> Candidate | None:
    url = item.get("permalink_url")
    title = (item.get("title") or "").strip()
    if not url or not title:
        return None
    uploader = ((item.get("user") or {}).get("username") or "").strip()
    artwork = item.get("artwork_url") or ""
    return Candidate(
        source="soundcloud",
        url=url,
        title=title,
        # duration приходит в миллисекундах
        duration=int(item.get("duration") or 0) // 1000,
        artist=uploader or None,
        uploader=uploader or None,
        cover_url=artwork or None,
    )


def search_tracks(query: str, limit: int = 5) -> list[Candidate]:
    """Кандидаты SoundCloud. Пустой список — API не ответил, зовите запасной путь."""
    global _client_id
    with _lock:
        if _client_id is None:
            _client_id = _load_client_id()
        if _client_id is None:
            return []
        path = (
            f"/search/tracks?q={urllib.parse.quote(query)}"
            f"&client_id={_client_id}&limit={max(1, limit)}"
        )
        body = _request(path)
        if body is None:
            # Скорее всего протух client_id — обновляем и пробуем ещё раз
            _client_id = _load_client_id()
            if _client_id is None:
                return []
            path = (
                f"/search/tracks?q={urllib.parse.quote(query)}"
                f"&client_id={_client_id}&limit={max(1, limit)}"
            )
            body = _request(path)
            if body is None:
                return []
    try:
        collection = json.loads(body).get("collection") or []
    except ValueError:
        logger.warning("SoundCloud API: ответ не разобрался как JSON")
        return []
    candidates = [_to_candidate(item) for item in collection]
    return [item for item in candidates if item is not None]

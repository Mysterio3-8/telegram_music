"""Ограничение частоты запросов к API — в памяти процесса.

🔴 Зачем. У бота антифлуд есть (middlewares/throttling), у API не было ничего.
Авторизованный пользователь мог засыпать дорогие эндпоинты — /search/live
дёргает SoundCloud и YouTube, /search/fetch и /transfer ставят скачивания в
очередь Celery, — и на боксе 961 МБ с одним ядром это прямой DoS: воркер уже
трижды падал по OOM от всплесков нагрузки.

Хранилище в памяти, а не в Redis, сознательно — ровно как у бота: запись на диск
при флуде сама роняла прод (26.07). uvicorn здесь один процесс, общий счётчик не
нужен. За IP берём X-Real-IP (его ставит nginx, перезаписывая присланный
клиентом), иначе все за прокси слились бы в один адрес 127.0.0.1.

Ключ — ЧЕЛОВЕК, а не IP (цикл 2, 14.09). Мобильные операторы сажают сотни
абонентов на один внешний адрес (CGNAT), и лимит 120 в минуту на IP при росте
аудитории резал бы честных людей пачками: один открыл приложение — соседи по
вышке ловят 429. Поэтому:
- запрос с валидным JWT считается в ведро пользователя (120/мин, дорогие 20/мин);
- ВСЕ запросы с адреса — ещё и в потолок IP (600/мин): тот, кто наплодил
  аккаунтов, упирается в него;
- без токена (вход, подписанное аудио, вебхуки) — только потолок IP и узкое
  ведро дорогих путей по IP.

Чистый ASGI, а не BaseHTTPMiddleware: та оборачивает каждый ответ, включая
аудиопотоки по 64 КБ, лишним слоем задач и очередей — на одном ядре это
заметная доля CPU именно там, где его и так мало.
"""
import time
from collections import defaultdict, deque

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.api.security import decode_access_token

WINDOW = 60.0
GENERAL_LIMIT = 120          # любых запросов за минуту от одного пользователя
EXPENSIVE_LIMIT = 20         # запросов к дорогим путям за минуту
IP_LIMIT = 600               # потолок с одного адреса (CGNAT — сотни людей)

# Пути, каждый вызов которых стоит дорого: внешняя сеть или очередь скачивания.
# Проверяется префиксом, поэтому /search/live/{ref}/fetch тоже сюда попадает.
EXPENSIVE_PREFIXES = ("/search/live", "/search/fetch", "/transfer", "/premium/pay")

_SWEEP_EVERY = 120.0
_RETENTION = 180.0


def _user_key(headers: Headers) -> str | None:
    auth = headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        return None
    telegram_id = decode_access_token(auth[7:].strip())
    return f"u:{telegram_id}" if telegram_id is not None else None


class RateLimitMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self._ip: dict[str, deque[float]] = defaultdict(deque)
        self._general: dict[str, deque[float]] = defaultdict(deque)
        self._expensive: dict[str, deque[float]] = defaultdict(deque)
        self._last_sweep = time.monotonic()

    @staticmethod
    def _client(scope: Scope, headers: Headers) -> str:
        fwd = headers.get("x-real-ip") or headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[0].strip()
        client = scope.get("client")
        return client[0] if client else "?"

    def _sweep(self, now: float) -> None:
        # Как в антифлуде бота: без уборки словари растут вечно, каждый новый IP
        # и каждый пользователь оставляет запись навсегда.
        if now - self._last_sweep < _SWEEP_EVERY:
            return
        self._last_sweep = now
        cutoff = now - _RETENTION
        for store in (self._ip, self._general, self._expensive):
            for key in [k for k, q in store.items() if not q or q[-1] < cutoff]:
                store.pop(key, None)

    @staticmethod
    def _over(bucket: deque[float], now: float, limit: int) -> bool:
        while bucket and now - bucket[0] > WINDOW:
            bucket.popleft()
        bucket.append(now)
        return len(bucket) > limit

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        now = time.monotonic()
        self._sweep(now)
        headers = Headers(scope=scope)
        ip = self._client(scope, headers)
        user = _user_key(headers)
        path = scope.get("path", "")

        # Retry-After: без него клиент не знает, когда повторять, и долбит сразу
        retry = {"Retry-After": str(int(WINDOW))}
        ip_over = self._over(self._ip[ip], now, IP_LIMIT)
        user_over = user is not None and self._over(self._general[user], now, GENERAL_LIMIT)
        if ip_over or user_over:
            response = JSONResponse({"detail": "Слишком много запросов"}, status_code=429, headers=retry)
            await response(scope, receive, send)
            return
        if path.startswith(EXPENSIVE_PREFIXES) and self._over(
            self._expensive[user or f"ip:{ip}"], now, EXPENSIVE_LIMIT
        ):
            response = JSONResponse(
                {"detail": "Слишком часто, подождите минуту"}, status_code=429, headers=retry
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)

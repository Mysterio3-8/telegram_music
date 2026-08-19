"""Ограничение частоты запросов к API — в памяти процесса.

🔴 Зачем. У бота антифлуд есть (middlewares/throttling), у API не было ничего.
Авторизованный пользователь мог засыпать дорогие эндпоинты — /search/live
дёргает SoundCloud и YouTube, /search/fetch и /transfer ставят скачивания в
очередь Celery, — и на боксе 961 МБ с одним ядром это прямой DoS: воркер уже
трижды падал по OOM от всплесков нагрузки.

Хранилище в памяти, а не в Redis, сознательно — ровно как у бота: запись на диск
при флуде сама роняла прод (26.07). uvicorn здесь один процесс, общий счётчик не
нужен. За IP берём X-Real-IP (его ставит nginx), иначе все за прокси слились бы в
один адрес 127.0.0.1.

Два ведра. Общее защищает от шквала любых запросов; узкое — от злоупотребления
дорогими путями, где один запрос стоит секунд внешней сети или места в очереди.
Пороги с большим запасом над нормальным использованием: загрузка Mini App это
~7 запросов, дальше редкие обращения.
"""
import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

WINDOW = 60.0
GENERAL_LIMIT = 120          # любых запросов за минуту с одного IP
EXPENSIVE_LIMIT = 20         # запросов к дорогим путям за минуту

# Пути, каждый вызов которых стоит дорого: внешняя сеть или очередь скачивания.
# Проверяется префиксом, поэтому /search/live/{ref}/fetch тоже сюда попадает.
EXPENSIVE_PREFIXES = ("/search/live", "/search/fetch", "/transfer", "/premium/pay")

_SWEEP_EVERY = 120.0
_RETENTION = 180.0


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app) -> None:
        super().__init__(app)
        self._general: dict[str, deque[float]] = defaultdict(deque)
        self._expensive: dict[str, deque[float]] = defaultdict(deque)
        self._last_sweep = time.monotonic()

    def _client(self, request: Request) -> str:
        fwd = request.headers.get("x-real-ip") or request.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[0].strip()
        return request.client.host if request.client else "?"

    def _sweep(self, now: float) -> None:
        # Как в антифлуде бота: без уборки словари растут вечно, каждый новый IP
        # оставляет запись навсегда.
        if now - self._last_sweep < _SWEEP_EVERY:
            return
        self._last_sweep = now
        cutoff = now - _RETENTION
        for store in (self._general, self._expensive):
            for ip in [k for k, q in store.items() if not q or q[-1] < cutoff]:
                store.pop(ip, None)

    @staticmethod
    def _over(bucket: deque[float], now: float, limit: int) -> bool:
        while bucket and now - bucket[0] > WINDOW:
            bucket.popleft()
        bucket.append(now)
        return len(bucket) > limit

    async def dispatch(self, request: Request, call_next):
        now = time.monotonic()
        self._sweep(now)
        ip = self._client(request)
        path = request.url.path

        if self._over(self._general[ip], now, GENERAL_LIMIT):
            return JSONResponse({"detail": "Слишком много запросов"}, status_code=429)
        if path.startswith(EXPENSIVE_PREFIXES) and self._over(
            self._expensive[ip], now, EXPENSIVE_LIMIT
        ):
            return JSONResponse({"detail": "Слишком часто, подождите минуту"}, status_code=429)

        return await call_next(request)

"""Ограничение частоты API. У бота антифлуд был, у API — нет: дорогие пути на
боксе 961 МБ это прямой DoS."""
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.ratelimit import (
    EXPENSIVE_LIMIT,
    GENERAL_LIMIT,
    RateLimitMiddleware,
)


def _app() -> TestClient:
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware)

    @app.get("/premium/status")
    async def status():
        return {"ok": True}

    @app.get("/search/live")
    async def live():
        return {"ok": True}

    return TestClient(app)


def test_normal_use_passes():
    client = _app()
    for _ in range(10):
        assert client.get("/premium/status").status_code == 200


def test_general_flood_gets_429():
    client = _app()
    codes = [client.get("/premium/status").status_code for _ in range(GENERAL_LIMIT + 5)]
    assert 429 in codes
    # первые проходят, ограничение включается на превышении
    assert codes[0] == 200


def test_expensive_path_capped_tighter():
    """Дорогой путь упирается в лимит раньше общего: EXPENSIVE_LIMIT < GENERAL_LIMIT."""
    client = _app()
    codes = [client.get("/search/live").status_code for _ in range(EXPENSIVE_LIMIT + 3)]
    assert codes.count(200) <= EXPENSIVE_LIMIT
    assert 429 in codes


def test_different_ips_counted_separately():
    client = _app()
    for _ in range(EXPENSIVE_LIMIT + 3):
        client.get("/search/live", headers={"X-Real-IP": "1.1.1.1"})
    # другой IP не должен пострадать от чужого флуда
    assert client.get("/search/live", headers={"X-Real-IP": "2.2.2.2"}).status_code == 200

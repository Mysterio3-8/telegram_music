"""Ограничение частоты API. У бота антифлуд был, у API — нет: дорогие пути на
боксе 961 МБ это прямой DoS. С 14.09 ключ — пользователь, а у IP только потолок
(мобильный CGNAT сажает сотни людей на один адрес)."""
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from starlette.testclient import TestClient

from app.api.ratelimit import (
    EXPENSIVE_LIMIT,
    GENERAL_LIMIT,
    IP_LIMIT,
    RateLimitMiddleware,
)
from app.api.security import create_access_token


def _app() -> TestClient:
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware)

    @app.get("/premium/status")
    async def status():
        return {"ok": True}

    @app.get("/search/live")
    async def live():
        return {"ok": True}

    @app.get("/stream")
    async def stream():
        async def chunks():
            for _ in range(3):
                yield b"x" * 1024

        return StreamingResponse(chunks(), media_type="audio/mpeg")

    return TestClient(app)


def _auth(telegram_id: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(telegram_id)}"}


def test_normal_use_passes():
    client = _app()
    for _ in range(10):
        assert client.get("/premium/status", headers=_auth(1)).status_code == 200


def test_user_flood_gets_429_with_retry_after():
    client = _app()
    codes = [client.get("/premium/status", headers=_auth(1)).status_code for _ in range(GENERAL_LIMIT + 5)]
    assert codes[0] == 200
    assert 429 in codes


def test_neighbours_behind_one_ip_are_not_punished():
    """CGNAT: флудит один абонент — соседи по адресу продолжают слушать."""
    client = _app()
    for _ in range(GENERAL_LIMIT + 5):
        client.get("/premium/status", headers={**_auth(1), "X-Real-IP": "5.5.5.5"})
    assert client.get("/premium/status", headers={**_auth(2), "X-Real-IP": "5.5.5.5"}).status_code == 200


def test_ip_ceiling_stops_many_accounts():
    client = _app()
    codes = [
        client.get("/premium/status", headers={**_auth(1000 + i), "X-Real-IP": "6.6.6.6"}).status_code
        for i in range(IP_LIMIT + 5)
    ]
    assert codes.count(200) == IP_LIMIT
    assert 429 in codes


def test_anonymous_flood_hits_ip_ceiling():
    client = _app()
    codes = [client.get("/premium/status").status_code for _ in range(IP_LIMIT + 5)]
    assert codes[0] == 200
    assert 429 in codes


def test_forged_token_counts_as_anonymous():
    client = _app()
    bad = {"Authorization": "Bearer not-a-jwt", "X-Real-IP": "7.7.7.7"}
    for _ in range(GENERAL_LIMIT + 5):
        assert client.get("/premium/status", headers=bad).status_code == 200


def test_expensive_path_capped_tighter():
    """Дорогой путь упирается в лимит раньше общего: EXPENSIVE_LIMIT < GENERAL_LIMIT."""
    client = _app()
    codes = [client.get("/search/live", headers=_auth(1)).status_code for _ in range(EXPENSIVE_LIMIT + 3)]
    assert codes.count(200) <= EXPENSIVE_LIMIT
    assert 429 in codes


def test_different_ips_counted_separately():
    client = _app()
    for _ in range(EXPENSIVE_LIMIT + 3):
        client.get("/search/live", headers={"X-Real-IP": "1.1.1.1"})
    # другой IP не должен пострадать от чужого флуда
    assert client.get("/search/live", headers={"X-Real-IP": "2.2.2.2"}).status_code == 200


def test_streaming_passes_through():
    client = _app()
    response = client.get("/stream", headers=_auth(1))
    assert response.status_code == 200
    assert len(response.content) == 3 * 1024

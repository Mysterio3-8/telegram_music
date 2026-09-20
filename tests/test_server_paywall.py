"""Серверный пэйвол Mini App (решение владельца 14.09).

Пэйвол жил только в интерфейсе: бесплатный аккаунт получал весь API прямыми
запросами. Тест обходит ВСЕ маршруты приложения, поэтому новый эндпоинт, забытый
без require_premium, упадёт здесь, а не утечёт в прод.
"""
import re
from datetime import datetime, timedelta

import pytest_asyncio
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.app import create_app
from app.api.deps import get_db
from app.api.security import create_access_token
from app.config import settings
from app.db import models  # noqa: F401
from app.db.base import Base
from app.db.models import User

FREE_ID = 556
EXPIRED_ID = 557

# Открыто без Premium: вход, оплата, профиль, документы (документы — статика),
# гейт подписки (он показывается ДО пэйвола), вебхуки платёжек и подписанные
# ссылки на аудио (их выдают только закрытые эндпоинты).
OPEN_ROUTES = {
    ("POST", "/login"),
    ("GET", "/health"),
    ("POST", "/premium/pay"),
    ("POST", "/premium/trial"),
    ("GET", "/premium/status"),
    # аналитика: пэйвол и первые экраны видят как раз бесплатные (15.09)
    ("POST", "/analytics/events"),
    ("POST", "/premium/autorenew"),
    ("POST", "/webhook/yookassa"),
    ("POST", "/webhook/cryptopay"),
    ("GET", "/profile"),
    ("GET", "/profile/top"),
    ("GET", "/referral/top"),
    ("GET", "/languages"),
    ("POST", "/language"),
    ("GET", "/subscription/status"),
    ("POST", "/subscription/click/{channel_id}"),
    # тексты песен: смотреть может любой (решение владельца 19.09), а писать —
    # только админ, и это строже пэйвола: у POST своя проверка прав
    ("GET", "/tracks/{track_id}/lyrics"),
    ("POST", "/tracks/{track_id}/lyrics"),
    ("GET", "/tracks/{track_id}/audio"),
    ("GET", "/instrumentals/{instrumental_id}/audio"),
    ("GET", "/stream/{ref}"),
}


@pytest_asyncio.fixture
async def client():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as seed:
        seed.add_all(
            [
                User(telegram_id=FREE_ID, first_name="Free"),
                User(
                    telegram_id=EXPIRED_ID,
                    first_name="Expired",
                    premium=True,  # флаг остался, срок вышел
                    premium_until=datetime.utcnow() - timedelta(minutes=1),
                ),
            ]
        )
        await seed.commit()

    async def override_get_db():
        async with factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app), app
    app.dependency_overrides.clear()
    await engine.dispose()


def _flatten(routes):
    # FastAPI 0.141 кладёт подключённые роутеры обёрткой _IncludedRouter: без
    # разворачивания в app.routes видны только /health и /docs, и тест молча
    # проверял бы пустоту (так и было в первой версии).
    for route in routes:
        if isinstance(route, APIRoute):
            yield route
        elif hasattr(route, "original_router"):
            yield from _flatten(route.original_router.routes)


def _routes(app):
    for route in _flatten(app.routes):
        for method in route.methods:
            yield method, route.path


def test_route_walk_sees_routers(client):
    _, app = client
    assert len(set(_routes(app))) > 50


def _auth(telegram_id: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(telegram_id)}"}


def test_every_closed_route_requires_premium(client):
    http, app = client
    leaked = []
    for method, path in _routes(app):
        if (method, path) in OPEN_ROUTES:
            continue
        url = re.sub(r"\{[^}]+\}", "1", path)
        for telegram_id in (FREE_ID, EXPIRED_ID):
            response = http.request(method, url, headers=_auth(telegram_id))
            if response.status_code != 402:
                leaked.append(f"{method} {path} [{telegram_id}] → {response.status_code}")
    assert not leaked, "Маршруты без пэйвола:\n" + "\n".join(leaked)


def test_open_routes_list_is_not_stale(client):
    _, app = client
    existing = set(_routes(app))
    assert OPEN_ROUTES - existing == set()


def test_free_user_still_reaches_paywall_endpoints(client):
    http, _ = client
    assert http.get("/premium/status", headers=_auth(FREE_ID)).status_code == 200
    assert http.get("/profile", headers=_auth(FREE_ID)).status_code == 200


def test_admin_passes_paywall(client, monkeypatch):
    http, _ = client
    monkeypatch.setattr(settings, "admin_ids", str(FREE_ID))
    assert http.get("/library/ids", headers=_auth(FREE_ID)).status_code == 200


def test_trial_opens_app(client):
    http, _ = client
    assert http.get("/library/ids", headers=_auth(FREE_ID)).status_code == 402
    assert http.post("/premium/trial", headers=_auth(FREE_ID)).status_code == 200
    assert http.get("/library/ids", headers=_auth(FREE_ID)).status_code == 200

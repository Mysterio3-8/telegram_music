"""Документация API закрыта на проде (аудит снаружи 24.09).

/api/docs, /api/redoc и /api/openapi.json отдавались всем — полная карта
маршрутов для атакующего. Mini App она не нужна.
"""
from fastapi.testclient import TestClient

from app.api.app import create_app
from app.config import settings


def test_docs_are_closed_by_default(monkeypatch):
    monkeypatch.setattr(settings, "api_docs", False, raising=False)
    client = TestClient(create_app())
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404, path


def test_docs_can_be_opened_locally(monkeypatch):
    monkeypatch.setattr(settings, "api_docs", True, raising=False)
    client = TestClient(create_app())
    assert client.get("/openapi.json").status_code == 200

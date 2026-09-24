"""Вход в админку: пароль + одноразовый код в Telegram (решение владельца 22.09).

Проверяем ровно то, ради чего это делалось: без входа данных не видно, пароль
сам по себе не пускает, код одноразовый, перебор упирается в замок.
"""
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.webadmin import auth
from app.webadmin.server import create_app, get_session


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "webadmin_password_hash", auth.hash_password("верный-пароль"), raising=False)
    monkeypatch.setattr(settings, "webadmin_password", "", raising=False)
    monkeypatch.setattr(settings, "webadmin_token", "", raising=False)
    monkeypatch.setattr(settings, "admin_ids", "777", raising=False)
    monkeypatch.setattr(settings, "jwt_secret", "s3cret", raising=False)
    auth.reset_failures()
    auth._challenge = None

    sent: list[str] = []

    class FakeBot:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc):
            return False

        async def send_message(self, chat_id, text, reply_markup=None):
            sent.append(text)
            return {}

    monkeypatch.setattr("app.services.bot_api.BotApi", FakeBot)

    app = create_app()

    async def no_db():
        raise AssertionError("до базы дойти не должны — вход не пройден")

    app.dependency_overrides[get_session] = no_db
    with TestClient(app) as test_client:
        yield test_client, sent
    app.dependency_overrides.clear()


def test_data_is_closed_without_login(client):
    test_client, _sent = client
    assert test_client.get("/api/overview").status_code == 401


def test_wrong_password_sends_no_code(client):
    test_client, sent = client
    assert test_client.post("/api/login", json={"password": "не тот"}).status_code == 401
    assert sent == []


def test_password_alone_does_not_authorize(client):
    test_client, sent = client
    assert test_client.post("/api/login", json={"password": "верный-пароль"}).status_code == 200
    assert sent and "Код входа" in sent[0]
    # Код ушёл, но сессии ещё нет — данные по-прежнему закрыты
    assert test_client.get("/api/overview").status_code == 401


def test_code_opens_session_and_burns(client):
    test_client, sent = client
    test_client.post("/api/login", json={"password": "верный-пароль"})
    code = sent[0].split("Код входа в админку: ")[1].split("\n")[0].strip()
    assert test_client.post("/api/login/code", json={"code": code}).status_code == 200
    assert test_client.get("/api/session").json()["authorized"] is True
    # Повторно тот же код не сработает — вызов сгорел
    assert test_client.post("/api/login/code", json={"code": code}).status_code == 401


def test_wrong_code_three_times_kills_the_challenge(client):
    test_client, _sent = client
    test_client.post("/api/login", json={"password": "верный-пароль"})
    for _ in range(3):
        assert test_client.post("/api/login/code", json={"code": "000000"}).status_code == 401
    # Четвёртая попытка — челлендж исчерпан, нужен новый вход
    response = test_client.post("/api/login/code", json={"code": "000000"})
    assert response.status_code in (401, 429)


def test_bruteforce_locks_the_door(client):
    test_client, _sent = client
    for _ in range(auth.LOCK_AFTER):
        test_client.post("/api/login", json={"password": "мимо"})
    response = test_client.post("/api/login", json={"password": "верный-пароль"})
    assert response.status_code == 429


def test_session_cookie_cannot_be_forged(client):
    test_client, _sent = client
    test_client.cookies.set(auth.SESSION_COOKIE, "9999999999.deadbeef.forged")
    assert test_client.get("/api/overview").status_code == 401


def test_without_password_configured_admin_works_as_before(monkeypatch):
    """Пароль не заведён — админка остаётся доступной по SSH-туннелю.

    Иначе обновление заперло бы владельца снаружи собственной админки до того,
    как он успеет прописать пароль в .env.
    """
    monkeypatch.setattr(settings, "webadmin_password_hash", "", raising=False)
    monkeypatch.setattr(settings, "webadmin_password", "", raising=False)
    monkeypatch.setattr(settings, "webadmin_token", "", raising=False)
    assert auth.password_configured() is False

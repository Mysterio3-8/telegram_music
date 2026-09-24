"""Вход в веб-админку: пароль плюс одноразовый код в Telegram (22.09).

Владелец выбрал этот вариант сам: «Пароль + код в Telegram». Смысл — чтобы
утёкший пароль сам по себе ничего не давал: второй ключ приходит в его личный
чат с ботом, а туда нужен доступ к его Telegram-аккаунту.

Рубежи, снизу вверх:
1. админка слушает только 127.0.0.1 на сервере и в nginx не заведена — из
   интернета её нет вовсе, доступ только через SSH-туннель (то есть по ключу);
2. пароль — `WEBADMIN_PASSWORD_HASH` (pbkdf2) или `WEBADMIN_PASSWORD`;
3. одноразовый код в Telegram, живёт 5 минут и сгорает после первой попытки;
4. сессия — подписанная HMAC-кука со сроком, её нельзя подделать без секрета.

⚠️ Счётчик попыток общий, а не по пользователям: админка одна, и «замедлить
всех» здесь то же самое, что «замедлить взломщика». После LOCK_AFTER неудач
вход закрывается на LOCK_MINUTES, о чём честно пишется в ответе.

⚠️ Коды и сессии живут в памяти процесса: рестарт админки разлогинивает.
Так и задумано — отдельное хранилище ради удобства здесь было бы лишней
поверхностью атаки.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import time

from fastapi import Cookie, HTTPException, status

from app.config import settings

logger = logging.getLogger(__name__)

SESSION_COOKIE = "admin_session"
SESSION_TTL_SECONDS = 12 * 3600
CODE_TTL_SECONDS = 300
CODE_ATTEMPTS = 3
LOCK_AFTER = 5
LOCK_MINUTES = 15
PBKDF2_ROUNDS = 200_000


class AuthError(HTTPException):
    def __init__(self, detail: str, code: int = status.HTTP_401_UNAUTHORIZED) -> None:
        super().__init__(code, detail)


# --- пароль ---


def hash_password(password: str, salt: str | None = None) -> str:
    """Строка для .env: «pbkdf2$<соль>$<хеш>». Соль случайная, если не задана."""
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), PBKDF2_ROUNDS)
    return f"pbkdf2${salt}${digest.hex()}"


def verify_password(password: str) -> bool:
    stored = (getattr(settings, "webadmin_password_hash", "") or "").strip()
    if stored.startswith("pbkdf2$"):
        try:
            _, salt, expected = stored.split("$", 2)
        except ValueError:
            logger.error("WEBADMIN_PASSWORD_HASH испорчен — вход невозможен")
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), PBKDF2_ROUNDS)
        return hmac.compare_digest(digest.hex(), expected)
    plain = (getattr(settings, "webadmin_password", "") or "").strip()
    if not plain:
        return False
    return hmac.compare_digest(password, plain)


def password_configured() -> bool:
    return bool(
        (getattr(settings, "webadmin_password_hash", "") or "").strip()
        or (getattr(settings, "webadmin_password", "") or "").strip()
    )


# --- защита от перебора ---

_failures: list[float] = []


def _locked_until() -> float:
    recent = [t for t in _failures if t > time.time() - LOCK_MINUTES * 60]
    _failures[:] = recent
    if len(recent) >= LOCK_AFTER:
        return recent[-1] + LOCK_MINUTES * 60
    return 0.0


def raise_if_locked() -> None:
    until = _locked_until()
    if until:
        minutes = max(1, int((until - time.time()) / 60) + 1)
        raise AuthError(f"Слишком много попыток. Вход закрыт на {minutes} мин.", status.HTTP_429_TOO_MANY_REQUESTS)


def note_failure() -> None:
    _failures.append(time.time())


def reset_failures() -> None:
    _failures.clear()


# --- одноразовый код ---

_challenge: dict | None = None


def start_challenge() -> str:
    """Создаёт код и возвращает его — отправка в Telegram делается снаружи."""
    global _challenge
    code = f"{secrets.randbelow(1_000_000):06d}"
    _challenge = {"code": code, "until": time.time() + CODE_TTL_SECONDS, "left": CODE_ATTEMPTS}
    return code


def check_challenge(code: str) -> bool:
    global _challenge
    if not _challenge or _challenge["until"] < time.time():
        _challenge = None
        raise AuthError("Код истёк — начните вход заново")
    if _challenge["left"] <= 0:
        _challenge = None
        raise AuthError("Код исчерпан — начните вход заново")
    _challenge["left"] -= 1
    if hmac.compare_digest(code.strip(), _challenge["code"]):
        _challenge = None
        return True
    return False


def challenge_pending() -> bool:
    return bool(_challenge and _challenge["until"] >= time.time())


# --- сессия ---


def _secret() -> bytes:
    raw = (
        (getattr(settings, "webadmin_token", "") or "")
        + (getattr(settings, "jwt_secret", "") or "")
        + (getattr(settings, "bot_token", "") or "")
    )
    if not raw:
        raise AuthError("Админка не настроена: нет ни одного секрета", status.HTTP_503_SERVICE_UNAVAILABLE)
    return hashlib.sha256(raw.encode()).digest()


def issue_session() -> str:
    expires = int(time.time()) + SESSION_TTL_SECONDS
    nonce = secrets.token_hex(8)
    body = f"{expires}.{nonce}"
    signature = hmac.new(_secret(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{signature}"


def valid_session(token: str | None) -> bool:
    if not token:
        return False
    try:
        expires_raw, nonce, signature = token.split(".", 2)
        expires = int(expires_raw)
    except (ValueError, AttributeError):
        return False
    if expires < time.time():
        return False
    body = f"{expires_raw}.{nonce}"
    expected = hmac.new(_secret(), body.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


async def require_session(admin_session: str | None = Cookie(default=None)) -> None:
    """Зависимость для всех данных админки. Без живой сессии — 401."""
    if not valid_session(admin_session):
        raise AuthError("Нужен вход")

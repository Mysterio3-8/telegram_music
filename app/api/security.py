import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl

import jwt

from app.config import settings


def validate_init_data(init_data: str) -> dict | None:
    """Проверяет подпись Telegram WebApp initData. Возвращает данные пользователя или None."""
    try:
        parsed = dict(parse_qsl(init_data, strict_parsing=True))
    except ValueError:
        return None

    received_hash = parsed.pop("hash", None)
    if not received_hash:
        return None

    data_check_string = "\n".join(f"{key}={parsed[key]}" for key in sorted(parsed))
    secret_key = hmac.new(b"WebAppData", settings.bot_token.encode(), hashlib.sha256).digest()
    computed = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(computed, received_hash):
        return None

    user_raw = parsed.get("user")
    if not user_raw:
        return None
    try:
        return json.loads(user_raw)
    except json.JSONDecodeError:
        return None


def create_access_token(telegram_id: int) -> str:
    payload = {
        "sub": str(telegram_id),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_ttl_minutes),
    }
    return jwt.encode(payload, settings.effective_jwt_secret, algorithm="HS256")


def decode_access_token(token: str) -> int | None:
    try:
        payload = jwt.decode(token, settings.effective_jwt_secret, algorithms=["HS256"])
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None


# --- Подписанные аудио-ссылки Mini App ---
# <audio src> не умеет слать Authorization-заголовок, поэтому доступ к байтам трека
# защищается HMAC-подписью с истечением: без личных данных в URL, срок жизни ограничен.

AUDIO_URL_TTL_SECONDS = 6 * 3600


def _audio_signature(track_id: int, expires: int, kind: str = "audio") -> str:
    # kind разделяет пространства подписей: подпись трека не годится для минуса
    payload = f"{kind}:{track_id}:{expires}"
    digest = hmac.new(settings.effective_jwt_secret.encode(), payload.encode(), hashlib.sha256)
    return digest.hexdigest()[:32]


def build_audio_url(track_id: int) -> str:
    expires = int(datetime.now(timezone.utc).timestamp()) + AUDIO_URL_TTL_SECONDS
    signature = _audio_signature(track_id, expires)
    return f"/tracks/{track_id}/audio?exp={expires}&sig={signature}"


def build_instrumental_audio_url(instrumental_id: int) -> str:
    expires = int(datetime.now(timezone.utc).timestamp()) + AUDIO_URL_TTL_SECONDS
    signature = _audio_signature(instrumental_id, expires, kind="ins")
    return f"/instrumentals/{instrumental_id}/audio?exp={expires}&sig={signature}"


def verify_audio_signature(track_id: int, expires: int, signature: str, kind: str = "audio") -> bool:
    if expires < int(datetime.now(timezone.utc).timestamp()):
        return False
    return hmac.compare_digest(_audio_signature(track_id, expires, kind), signature)

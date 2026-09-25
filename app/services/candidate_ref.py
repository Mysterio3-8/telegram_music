"""Ссылка на кандидата живого поиска для Mini App.

Кандидат не записан в базу — по определению: строка появляется только когда трек
реально отдан пользователю. Значит ссылаться на него по id нельзя, а класть
исходный URL источника в открытый параметр — значит отдать чужому клиенту
управление тем, что мы пойдём скачивать.

Поэтому ref самодостаточен: внутри лежат метаданные кандидата и срок жизни, всё
вместе подписано тем же секретом, что и аудио-ссылки. Сервер ничего не хранит,
подделать нельзя, протухает само.

В боте эта схема не годится: Telegram даёт под callback_data 64 байта — там
кандидаты живут в FSM.
"""
import base64
import binascii
import hashlib
import hmac
import json
from dataclasses import asdict
from datetime import datetime, timezone

from app.config import settings
from app.services.track_lookup.ranking import Candidate

REF_TTL_SECONDS = 6 * 3600


def _sign(body: str) -> str:
    digest = hmac.new(settings.effective_jwt_secret.encode(), body.encode(), hashlib.sha256)
    return digest.hexdigest()[:32]


def encode_ref(
    candidate: Candidate, ttl_seconds: int = REF_TTL_SECONDS, owner: int | None = None
) -> str:
    """owner — telegram_id того, кому выдан ref. Кладётся только превью Go+:
    поток по такой ссылке не играет, а импортирует полную копию от имени
    человека, а `<audio src>` не несёт с собой токен входа."""
    payload = {
        **asdict(candidate),
        "exp": int(datetime.now(timezone.utc).timestamp()) + ttl_seconds,
    }
    if owner:
        payload["own"] = int(owner)
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    body = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    return f"{body}.{_sign(body)}"


def decode_ref(ref: str) -> Candidate | None:
    """Кандидат из ref или None: подпись не сошлась, срок вышел, формат битый."""
    body, _, signature = (ref or "").partition(".")
    if not body or not signature or not hmac.compare_digest(_sign(body), signature):
        return None
    try:
        padded = body + "=" * (-len(body) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))
    except (binascii.Error, ValueError):
        return None
    if int(payload.pop("exp", 0)) < int(datetime.now(timezone.utc).timestamp()):
        return None
    payload.pop("own", None)
    try:
        return Candidate(**payload)
    except TypeError:  # ref от другой версии Candidate
        return None


def ref_owner(ref: str) -> int | None:
    """telegram_id владельца из ПРОВЕРЕННОГО ref (см. encode_ref); None — нет."""
    if decode_ref(ref) is None:
        return None
    body = ref.partition(".")[0]
    payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    owner = payload.get("own")
    return int(owner) if isinstance(owner, int) and owner > 0 else None

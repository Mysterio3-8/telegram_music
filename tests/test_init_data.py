"""Проверка initData Telegram WebApp — вход в Mini App.

🔴 Подпись подтверждает, что строку выдал Telegram, но НЕ говорит когда. Пока
свежесть не проверялась, перехваченная initData (лог, скриншот, чужое
устройство) оставалась годной навсегда: по ней бесконечно выпускались токены на
чужой аккаунт.
"""
import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

from app.api.security import INIT_DATA_TTL_SECONDS, validate_init_data
from app.config import settings

BOT_TOKEN = "123456:TEST-TOKEN"


def make_init_data(auth_date: int, user_id: int = 42, token: str = BOT_TOKEN) -> str:
    """Собирает initData ровно так, как это делает Telegram."""
    fields = {
        "auth_date": str(auth_date),
        "query_id": "AAF",
        "user": json.dumps({"id": user_id, "first_name": "Илья"}, ensure_ascii=False),
    }
    check_string = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


def test_fresh_init_data_passes(monkeypatch):
    monkeypatch.setattr(settings, "bot_token", BOT_TOKEN)

    data = validate_init_data(make_init_data(int(time.time())))

    assert data is not None and data["id"] == 42


def test_stale_init_data_is_rejected(monkeypatch):
    """Главная починка: строка старше суток больше не пускает в аккаунт."""
    monkeypatch.setattr(settings, "bot_token", BOT_TOKEN)
    old = int(time.time()) - INIT_DATA_TTL_SECONDS - 60

    assert validate_init_data(make_init_data(old)) is None


def test_init_data_just_inside_window_passes(monkeypatch):
    """Сутки, а не час: Mini App переиспользует initData, когда истекает JWT, и
    короткое окно отрезало бы человека с давно открытым приложением."""
    monkeypatch.setattr(settings, "bot_token", BOT_TOKEN)
    almost = int(time.time()) - INIT_DATA_TTL_SECONDS + 300

    assert validate_init_data(make_init_data(almost)) is not None


def test_missing_auth_date_is_rejected(monkeypatch):
    """Без метки времени судить о свежести нечем — не пускаем."""
    monkeypatch.setattr(settings, "bot_token", BOT_TOKEN)
    fields = {"user": json.dumps({"id": 42})}
    check_string = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()

    assert validate_init_data(urlencode(fields)) is None


def test_forged_auth_date_is_rejected(monkeypatch):
    """Подделать метку нельзя: она входит в подпись, и проверка свежести идёт
    ПОСЛЕ сверки подписи."""
    monkeypatch.setattr(settings, "bot_token", BOT_TOKEN)
    honest = make_init_data(int(time.time()) - INIT_DATA_TTL_SECONDS - 60)
    tampered = honest.replace(
        f"auth_date={int(time.time()) - INIT_DATA_TTL_SECONDS - 60}",
        f"auth_date={int(time.time())}",
    )

    assert validate_init_data(tampered) is None


def test_wrong_token_is_rejected(monkeypatch):
    """Подпись чужим токеном не проходит — базовая гарантия, не сломана."""
    monkeypatch.setattr(settings, "bot_token", BOT_TOKEN)

    assert validate_init_data(make_init_data(int(time.time()), token="999:OTHER")) is None

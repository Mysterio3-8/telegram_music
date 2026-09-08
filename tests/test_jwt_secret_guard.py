"""Токены Mini App нельзя подписывать пустым ключом.

🔴 Поймано первым прогоном в CI, и локально это было невидимо: PyJWT до 2.10
молча подписывал пустым ключом (в песочнице стоял 2.7.0), а с 2.10 запрещает.
requirements допускают обе версии (`pyjwt>=2.9`), поэтому полагаться на
библиотеку нельзя — отказываем сами.

Почему это дыра, а не мелочь: подпись пустым ключом воспроизводится кем угодно,
то есть любой человек мог бы выписать себе токен на чужой аккаунт.
"""
import pytest

from app.config import settings


def test_secret_falls_back_to_bot_token(monkeypatch):
    monkeypatch.setattr(settings, "jwt_secret", "")
    monkeypatch.setattr(settings, "bot_token", "123:abc")
    assert settings.effective_jwt_secret == "123:abc"


def test_explicit_secret_wins_over_bot_token(monkeypatch):
    monkeypatch.setattr(settings, "jwt_secret", "своя-подпись")
    monkeypatch.setattr(settings, "bot_token", "123:abc")
    assert settings.effective_jwt_secret == "своя-подпись"


def test_empty_secret_is_refused_loudly(monkeypatch):
    """Ни на какой версии PyJWT пустой ключ не должен доехать до подписи."""
    monkeypatch.setattr(settings, "jwt_secret", "")
    monkeypatch.setattr(settings, "bot_token", "")
    with pytest.raises(RuntimeError, match="подделать"):
        _ = settings.effective_jwt_secret

"""Отсутствие telethon не должно мешать боту и воркерам запускаться.

Зачем тест: подсистема чтения ТГ-канала опциональна — каждый её вызов закрыт
проверкой `is_configured()`, а админский экран честно пишет, что вход не
настроен. Но импорт был жёстким, и модуль тянется из `app/main.py` (роутер
admin_telegram_channel) и из `app/tasks/celery_app.py`. То есть не доехавший
или сломанный telethon уронил бы бота И все воркеры на старте — до того, как
появится хоть один обработчик ошибок, и без единой строки в журнале о причине.
"""
import builtins
import importlib
import sys

import pytest

_TELETHON_MODULES = [name for name in sys.modules if name.split(".")[0] == "telethon"]


@pytest.fixture()
def without_telethon(monkeypatch):
    """Прячет telethon так, как будто он не установлен."""
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "telethon" or name.startswith("telethon."):
            raise ModuleNotFoundError(f"No module named '{name}'")
        return real_import(name, *args, **kwargs)

    for name in _TELETHON_MODULES:
        monkeypatch.delitem(sys.modules, name, raising=False)
    monkeypatch.setattr(builtins, "__import__", fake_import)
    yield


def _reload(module_name: str):
    sys.modules.pop(module_name, None)
    return importlib.import_module(module_name)


def test_client_module_imports_without_telethon(without_telethon):
    client = _reload("app.services.telegram_channel.client")
    # Без библиотеки подсистема отвечает «не настроена», а не падает: вызывающий
    # код уходит в свою обычную ветку отказа.
    assert client.is_configured() is False
    with pytest.raises(RuntimeError, match="telethon"):
        client.build_client()


@pytest.mark.parametrize(
    "module_name",
    [
        "app.services.telegram_channel.scanner",
        "app.services.telegram_channel.importer",
    ],
)
def test_annotation_only_modules_import_without_telethon(without_telethon, module_name):
    # TelegramClient здесь только аннотация типа — тянуть библиотеку в рантайме незачем.
    assert _reload(module_name) is not None

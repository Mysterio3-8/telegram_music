"""Процесс API не загружает aiogram (цикл 7, 15.09).

aiogram.types+methods — +38 МБ, 42% Python-кучи API и 6.5 из 8.6 сек импорта.
Бот и воркеры живут на aiogram, API — на лёгком клиенте (services/bot_api.py).
Один случайный `from aiogram import Bot` сверху в сервисе, который API
импортирует, молча вернул бы всю цену — поэтому проверка в тестах.
"""
import fnmatch
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_api_app_does_not_import_aiogram():
    code = (
        "import sys; import app.api.app; "
        "print(','.join(sorted(m for m in sys.modules if m == 'aiogram' or m.startswith('aiogram.'))[:5]))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    assert result.stdout.strip() == "", f"API тянет aiogram: {result.stdout.strip()}"


def _worker_queue(celery_app, name: str) -> str:
    """Очередь, в которую задачу положил бы сам воркерный celery_app: маршруты
    task_routes (точные, затем шаблоны) важнее `queue=` из декоратора."""
    routes = celery_app.conf.task_routes or {}
    if name in routes:
        return routes[name]["queue"]
    for pattern, route in routes.items():
        if fnmatch.fnmatchcase(name, pattern):
            return route["queue"]
    return celery_app.tasks[name].queue or "celery"


def test_queue_client_matches_worker_tasks():
    from app.tasks.celery_app import celery_app
    from app.tasks.queue_client import QUEUES

    for name, queue in QUEUES.items():
        assert name in celery_app.tasks, f"задачи {name} нет у воркера"
        assert queue == _worker_queue(celery_app, name), name


def test_enqueue_sends_by_name_to_queue(monkeypatch):
    from app.tasks import queue_client

    sent = []

    class FakeApp:
        def send_task(self, name, args=(), kwargs=None, queue=None):
            sent.append((name, args, kwargs, queue))

    monkeypatch.setattr(queue_client, "_app", lambda: FakeApp())
    queue_client.enqueue("transfer.playlist", [{"artist": "A", "title": "B"}], 7)
    queue_client.enqueue("search.repair_track", track_id=5)
    assert sent == [
        ("transfer.playlist", ([{"artist": "A", "title": "B"}], 7), {}, "celery"),
        ("search.repair_track", (), {"track_id": 5}, "youtube_user"),
    ]

"""Кнопка «📊 Аналитика» в админке: отчёт без SSH (15.09)."""
from types import SimpleNamespace

from app.handlers import admin as admin_handlers
from app.keyboards.admin import admin_panel_keyboard


def test_admin_panel_has_analytics_button():
    data = [b.callback_data for row in admin_panel_keyboard().inline_keyboard for b in row]
    assert "adm:analytics:7" in data


async def test_analytics_callback_sends_report_to_admin(monkeypatch):
    sent: list[tuple[str, object]] = []
    answers: list[str] = []

    async def answer_message(text, reply_markup=None):
        sent.append((text, reply_markup))

    async def answer_callback(text=None, show_alert=False):
        answers.append(text)

    async def fake_report(session, days):
        return SimpleNamespace(days=days)

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    import app.cli.analytics as analytics_cli

    monkeypatch.setattr(admin_handlers, "is_admin", lambda _id: True)
    monkeypatch.setattr(admin_handlers, "session_factory", FakeSession)
    monkeypatch.setattr(analytics_cli, "build_analytics_report", fake_report)
    monkeypatch.setattr(analytics_cli, "format_report", lambda r: "\n".join([f"отчёт {r.days}"] + ["x" * 50] * 200))

    callback = SimpleNamespace(
        data="adm:analytics:30",
        from_user=SimpleNamespace(id=1),
        message=SimpleNamespace(answer=answer_message),
        answer=answer_callback,
    )
    await admin_handlers.cb_admin_analytics(callback)

    assert answers == ["Считаю…"]
    assert len(sent) >= 2 and sent[0][0].startswith("отчёт 30")
    assert all(len(text) <= 4096 for text, _ in sent)
    assert all(markup is None for _, markup in sent[:-1]) and sent[-1][1] is not None


async def test_analytics_callback_rejects_non_admin(monkeypatch):
    answers = []

    async def answer_callback(text=None, show_alert=False):
        answers.append((text, show_alert))

    monkeypatch.setattr(admin_handlers, "is_admin", lambda _id: False)
    callback = SimpleNamespace(data="adm:analytics:7", from_user=SimpleNamespace(id=2), answer=answer_callback)
    await admin_handlers.cb_admin_analytics(callback)
    assert answers == [("Недоступно", True)]

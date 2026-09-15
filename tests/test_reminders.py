"""Напоминания «продлите Premium бесплатно» (15.09)."""
from datetime import datetime, timedelta

from sqlalchemy import func, select

from app.config import settings
from app.db.models import User, UserReminder
from app.services.bot_api import BotApiError
from app.services.reminders import reminder_kind, send_due_reminders

NOW = datetime(2026, 9, 15, 4, 0, 0)


class FakeBot:
    def __init__(self, error: str | None = None) -> None:
        self.sent: list[tuple[int, str, dict]] = []
        self.error = error

    async def send_message(self, chat_id, text, reply_markup=None):
        if self.error:
            raise BotApiError(f"sendMessage: {self.error}")
        self.sent.append((chat_id, text, reply_markup))
        return {}


async def _user(session, telegram_id: int, left: timedelta | None, **extra) -> User:
    user = User(
        telegram_id=telegram_id,
        premium=left is not None,
        premium_until=(NOW + left) if left is not None else None,
        trial_used=True,
        ui_language="ru",
        **extra,
    )
    session.add(user)
    await session.commit()
    return user


def test_windows():
    make = lambda left: User(telegram_id=1, premium_until=NOW + left)  # noqa: E731
    assert reminder_kind(make(timedelta(days=3, hours=12)), NOW) == "ends_in_4"
    assert reminder_kind(make(timedelta(hours=12)), NOW) == "ends_tomorrow"
    assert reminder_kind(make(-timedelta(hours=12)), NOW) == "ended"
    assert reminder_kind(make(timedelta(days=5)), NOW) is None
    assert reminder_kind(make(timedelta(days=2)), NOW) is None
    assert reminder_kind(make(-timedelta(days=2)), NOW) is None
    assert reminder_kind(User(telegram_id=1), NOW) is None


async def test_sends_once_with_referral_link_and_buttons(session, monkeypatch):
    monkeypatch.setattr(settings, "bot_username", "muz_damn_bot")
    monkeypatch.setattr(settings, "public_base_url", "https://example.org")
    user = await _user(session, 1001, timedelta(days=3, hours=6))
    bot = FakeBot()

    report = await send_due_reminders(session, bot, now=NOW)
    assert report.sent == 1 and report.by_kind == {"ends_in_4": 1}
    chat_id, text, markup = bot.sent[0]
    assert chat_id == user.telegram_id
    assert "Премиум" not in text and "Premium" in text
    assert "https://t.me/muz_damn_bot?start=ref_1001" in text
    assert "Друзей до награды: 1 → +1 дн." in text
    buttons = [b for row in markup["inline_keyboard"] for b in row]
    assert buttons[0]["url"].startswith("https://t.me/share/url?url=")
    assert buttons[1]["web_app"]["url"] == "https://example.org"

    again = await send_due_reminders(session, bot, now=NOW + timedelta(hours=1))
    assert again.due == 0 and len(bot.sent) == 1


async def test_dry_run_writes_nothing(session):
    await _user(session, 1002, timedelta(hours=10))
    bot = FakeBot()
    report = await send_due_reminders(session, bot, now=NOW, dry=True)
    assert report.due == 1 and bot.sent == []
    assert await session.scalar(select(func.count()).select_from(UserReminder)) == 0


async def test_blocked_user_is_marked_and_not_retried(session):
    user = await _user(session, 1003, -timedelta(hours=3))
    report = await send_due_reminders(session, FakeBot("Forbidden: bot was blocked by the user"), now=NOW)
    assert report.blocked == 1
    await session.refresh(user)
    assert user.bot_blocked is True
    assert (await send_due_reminders(session, FakeBot(), now=NOW)).due == 0


async def test_temporary_failure_is_retried_next_run(session):
    await _user(session, 1004, timedelta(hours=5))
    failed = await send_due_reminders(session, FakeBot("Too Many Requests: retry after 5"), now=NOW)
    assert failed.failed == 1
    retry = FakeBot()
    assert (await send_due_reminders(session, retry, now=NOW)).sent == 1


async def test_skips_admins_and_far_dates(session, monkeypatch):
    admin = await _user(session, 1005, timedelta(hours=5))
    monkeypatch.setattr(type(settings), "admin_id_set", property(lambda _self: {admin.telegram_id}))
    await _user(session, 1006, timedelta(days=6))
    await _user(session, 1007, None)
    report = await send_due_reminders(session, FakeBot(), now=NOW)
    assert report.due == 0

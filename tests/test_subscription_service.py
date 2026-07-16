from datetime import datetime, timedelta, timezone

from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramAPIError

from app.config import settings
from app.db.models import SubscriptionStatus, User
from app.services.subscription import (
    check_channel_membership,
    is_channel_subscribed,
    is_fully_subscribed,
)


class FakeMember:
    def __init__(self, status: str) -> None:
        self.status = status


class FakeBot:
    def __init__(self, status: str | None = None, raise_error: bool = False) -> None:
        self.status = status
        self.raise_error = raise_error
        self.calls = 0

    async def get_chat_member(self, chat_id: str, user_id: int):
        self.calls += 1
        if self.raise_error:
            raise TelegramAPIError(method=None, message="boom")
        return FakeMember(self.status)


async def make_user(session) -> User:
    user = User(telegram_id=555)
    session.add(user)
    await session.commit()
    return user


async def test_check_channel_membership_true_for_member():
    bot = FakeBot(status=ChatMemberStatus.MEMBER)
    assert await check_channel_membership(bot, 1, "@chan") is True


async def test_check_channel_membership_false_for_left():
    bot = FakeBot(status=ChatMemberStatus.LEFT)
    assert await check_channel_membership(bot, 1, "@chan") is False


async def test_check_channel_membership_fail_closed_on_api_error():
    bot = FakeBot(raise_error=True)
    assert await check_channel_membership(bot, 1, "@chan") is False


async def test_is_channel_subscribed_uses_cache_within_ttl(session):
    user = await make_user(session)
    bot = FakeBot(status=ChatMemberStatus.MEMBER)

    first = await is_channel_subscribed(session, bot, user.id, user.telegram_id, "@chan")
    second = await is_channel_subscribed(session, bot, user.id, user.telegram_id, "@chan")

    assert first is True
    assert second is True
    assert bot.calls == 1  # второй вызов — из кэша


async def test_is_channel_subscribed_force_bypasses_cache(session):
    user = await make_user(session)
    row = SubscriptionStatus(
        user_id=user.id, channel="@chan", is_subscribed=True, checked_at=datetime.now(timezone.utc)
    )
    session.add(row)
    await session.commit()

    bot = FakeBot(status=ChatMemberStatus.LEFT)
    result = await is_channel_subscribed(session, bot, user.id, user.telegram_id, "@chan", force=True)

    assert result is False
    assert bot.calls == 1


async def test_is_channel_subscribed_refreshes_after_ttl(session):
    user = await make_user(session)
    stale = datetime.now(timezone.utc) - timedelta(minutes=settings.subscription_cache_ttl_minutes + 1)
    row = SubscriptionStatus(user_id=user.id, channel="@chan", is_subscribed=True, checked_at=stale)
    session.add(row)
    await session.commit()

    bot = FakeBot(status=ChatMemberStatus.LEFT)
    result = await is_channel_subscribed(session, bot, user.id, user.telegram_id, "@chan")

    assert result is False
    assert bot.calls == 1


async def _seed_channels(session, *channels: str) -> None:
    from app.services.required_channels import add_required_channel

    for channel in channels:
        await add_required_channel(session, channel, f"L{channel}")


async def test_is_fully_subscribed_requires_all_channels(session):
    await _seed_channels(session, "@chan1", "@chan2")
    user = await make_user(session)
    bot = FakeBot(status=ChatMemberStatus.MEMBER)

    assert await is_fully_subscribed(session, bot, user.id, user.telegram_id) is True
    assert bot.calls == 2  # оба канала проверены


async def test_is_fully_subscribed_false_when_one_channel_missing(session):
    await _seed_channels(session, "@chan1", "@chan2")
    user = await make_user(session)
    bot = FakeBot(status=ChatMemberStatus.LEFT)

    assert await is_fully_subscribed(session, bot, user.id, user.telegram_id) is False


async def test_is_fully_subscribed_true_when_no_channels(session):
    # пустой список каналов (админ всё удалил) → гейт выключен
    user = await make_user(session)
    bot = FakeBot(status=ChatMemberStatus.LEFT)

    assert await is_fully_subscribed(session, bot, user.id, user.telegram_id) is True
    assert bot.calls == 0


async def test_is_fully_subscribed_admin_bypass(session, monkeypatch):
    monkeypatch.setattr(settings, "admin_bypass_subscription", True)
    monkeypatch.setattr(settings, "admin_ids", "555")
    user = await make_user(session)
    bot = FakeBot(status=ChatMemberStatus.LEFT)

    assert await is_fully_subscribed(session, bot, user.id, user.telegram_id) is True
    assert bot.calls == 0

from app.db.models import SubscriptionStatus, User
from app.services.required_channels import (
    add_required_channel,
    get_required_channels,
    normalize_channel,
    remove_required_channel,
)


def test_normalize_channel():
    assert normalize_channel("@music") == "@music"
    assert normalize_channel("  @music  ") == "@music"
    assert normalize_channel("https://t.me/music") == "@music"
    assert normalize_channel("-1001234567890") == "-1001234567890"
    assert normalize_channel("music") is None
    assert normalize_channel("@") is None
    assert normalize_channel("-100abc") is None


async def test_add_list_remove_channel(session):
    row = await add_required_channel(session, "@chan", "Канал")
    assert row is not None

    # дубликат не создаётся
    assert await add_required_channel(session, "@chan", "Другое имя") is None

    channels = await get_required_channels(session)
    assert [(c.channel, c.label) for c in channels] == [("@chan", "Канал")]

    assert await remove_required_channel(session, row.id) is True
    assert await get_required_channels(session) == []
    assert await remove_required_channel(session, row.id) is False  # уже удалён


async def test_remove_channel_purges_subscription_cache(session):
    user = User(telegram_id=1)
    session.add(user)
    await session.flush()
    row = await add_required_channel(session, "@chan", "Канал")
    session.add(SubscriptionStatus(user_id=user.id, channel="@chan", is_subscribed=True))
    await session.commit()

    await remove_required_channel(session, row.id)

    assert await session.get(SubscriptionStatus, (user.id, "@chan")) is None


def test_normalize_bot_link_variants():
    from app.services.required_channels import normalize_bot_link

    assert normalize_bot_link("@some_bot") == "https://t.me/some_bot"
    assert normalize_bot_link("t.me/MusicBot") == "https://t.me/MusicBot"
    assert (
        normalize_bot_link("https://t.me/PartnerBot?start=ref123")
        == "https://t.me/PartnerBot?start=ref123"
    )
    assert normalize_bot_link("@channel_name") is None  # не оканчивается на bot
    assert normalize_bot_link("просто текст") is None


async def test_bot_rows_skipped_in_subscription_check(session, monkeypatch):
    """«ОП на ботов»: bot-строки не проверяются — гейт не блокируется навечно."""
    from unittest.mock import AsyncMock

    from app.db.models import User
    from app.services.required_channels import add_required_channel
    from app.services.subscription import is_fully_subscribed

    user = User(telegram_id=1)
    session.add(user)
    await session.commit()

    await add_required_channel(session, "https://t.me/PartnerBot", "🤖 Бот", kind="bot")

    # Каналов нет, только бот → подписка считается полной без вызовов Telegram
    bot = AsyncMock()
    assert await is_fully_subscribed(session, bot, user.id, user.telegram_id) is True
    bot.get_chat_member.assert_not_called()


async def test_gate_keyboard_includes_bot_url(session):
    from app.keyboards.subscription import subscription_gate_keyboard
    from app.services.required_channels import add_required_channel, get_required_channels

    await add_required_channel(session, "@music_channel", "📢 Канал")
    await add_required_channel(session, "https://t.me/PartnerBot?start=x", "🤖 Бот", kind="bot")

    keyboard = subscription_gate_keyboard(await get_required_channels(session))
    urls = [btn.url for row in keyboard.inline_keyboard for btn in row if btn.url]

    assert "https://t.me/music_channel" in urls
    assert "https://t.me/PartnerBot?start=x" in urls

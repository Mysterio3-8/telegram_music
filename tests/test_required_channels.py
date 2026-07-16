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

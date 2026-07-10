from app.services.users import (
    TelegramProfile,
    count_library_tracks,
    count_playlists,
    get_or_create_user,
    get_user_by_telegram_id,
)

PROFILE = TelegramProfile(telegram_id=100500, username="ivan", first_name="Иван", language="ru")


async def test_creates_user_on_first_login(session):
    user = await get_or_create_user(session, PROFILE)

    assert user.id is not None
    assert user.telegram_id == 100500
    assert user.username == "ivan"
    assert user.premium is False
    assert user.last_login is not None


async def test_returns_same_user_and_updates_profile_on_repeat_login(session):
    first = await get_or_create_user(session, PROFILE)
    updated_profile = TelegramProfile(
        telegram_id=100500, username="ivan_new", first_name="Иван", language="ru"
    )

    second = await get_or_create_user(session, updated_profile)

    assert second.id == first.id
    assert second.username == "ivan_new"


async def test_get_user_by_telegram_id_returns_none_for_unknown(session):
    assert await get_user_by_telegram_id(session, 999) is None


async def test_new_user_has_empty_counters(session):
    user = await get_or_create_user(session, PROFILE)

    assert await count_library_tracks(session, user.id) == 0
    assert await count_playlists(session, user.id) == 0

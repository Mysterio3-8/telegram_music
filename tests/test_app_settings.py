from app.services.app_settings import (
    YOUTUBE_IMPORT_ENABLED,
    is_youtube_enabled,
    set_flag,
)


async def test_youtube_enabled_defaults_true(session):
    assert await is_youtube_enabled(session) is True


async def test_toggle_persists(session):
    await set_flag(session, YOUTUBE_IMPORT_ENABLED, False)
    assert await is_youtube_enabled(session) is False

    await set_flag(session, YOUTUBE_IMPORT_ENABLED, True)
    assert await is_youtube_enabled(session) is True

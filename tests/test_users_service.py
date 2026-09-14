from sqlalchemy import select

from app.db.models import User
from app.services.users import (
    TelegramProfile,
    count_library_tracks,
    count_playlists,
    create_user,
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


async def test_create_user_survives_insert_race(session):
    # Имитация гонки: строка появилась между select и insert параллельным апдейтом
    session.add(User(telegram_id=100500))
    await session.commit()

    user = await create_user(session, 100500)

    assert user.telegram_id == 100500
    rows = (await session.scalars(select(User).where(User.telegram_id == 100500))).all()
    assert len(rows) == 1


async def test_get_user_by_telegram_id_returns_none_for_unknown(session):
    assert await get_user_by_telegram_id(session, 999) is None


async def test_new_user_has_empty_counters(session):
    user = await get_or_create_user(session, PROFILE)

    assert await count_library_tracks(session, user.id) == 0
    assert await count_playlists(session, user.id) == 0


async def test_repeat_action_without_changes_does_not_write(session, monkeypatch):
    """ensure_user зовётся почти из каждого хендлера: раньше это был commit на
    КАЖДОЕ действие в боте — пишущая транзакция SQLite без единого изменения."""
    await get_or_create_user(session, PROFILE)

    commits = []
    original_commit = session.commit

    async def counting_commit():
        commits.append(1)
        await original_commit()

    monkeypatch.setattr(session, "commit", counting_commit)
    for _ in range(5):
        await get_or_create_user(session, PROFILE)
    assert commits == []


async def test_profile_change_is_still_saved(session, monkeypatch):
    await get_or_create_user(session, PROFILE)
    renamed = TelegramProfile(
        telegram_id=PROFILE.telegram_id, username="renamed", first_name=PROFILE.first_name, language=PROFILE.language
    )
    user = await get_or_create_user(session, renamed)
    await session.refresh(user)
    assert user.username == "renamed"


async def test_stale_last_login_is_bumped(session):
    from datetime import datetime, timedelta

    user = await get_or_create_user(session, PROFILE)
    stale = datetime.utcnow() - timedelta(hours=2)  # наивное время — как отдаёт SQLite
    user.last_login = stale
    await session.commit()

    user = await get_or_create_user(session, PROFILE)
    await session.refresh(user)
    assert user.last_login > stale

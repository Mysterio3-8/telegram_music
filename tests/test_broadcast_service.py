from app.db.models import User
from app.services.broadcast import active_recipient_ids, mark_bot_blocked


async def test_recipients_exclude_blocked(session):
    session.add_all(
        [
            User(telegram_id=100, first_name="A"),
            User(telegram_id=200, first_name="B", bot_blocked=True),
            User(telegram_id=300, first_name="C"),
        ]
    )
    await session.commit()

    assert await active_recipient_ids(session) == [100, 300]


async def test_mark_bot_blocked(session):
    session.add(User(telegram_id=100, first_name="A"))
    await session.commit()

    await mark_bot_blocked(session, 100)

    assert await active_recipient_ids(session) == []


async def test_mark_unknown_user_is_noop(session):
    session.add(User(telegram_id=100, first_name="A"))
    await session.commit()

    await mark_bot_blocked(session, 999)  # нет такого — не падаем

    assert await active_recipient_ids(session) == [100]

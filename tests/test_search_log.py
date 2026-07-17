from app.db.models import User
from app.services.search_log import log_search_query, popular_queries


async def make_user(session, telegram_id=1) -> User:
    user = User(telegram_id=telegram_id)
    session.add(user)
    await session.commit()
    return user


async def test_log_rejects_junk(session):
    user = await make_user(session)

    assert not await log_search_query(session, user.id, "к")
    assert not await log_search_query(session, user.id, "x" * 200)
    assert await log_search_query(session, user.id, "  кино   группа ")

    top = await popular_queries(session)
    assert top == ["кино группа"]


async def test_popular_groups_case_insensitive(session):
    # Латиница: lower() в SQLite не берёт кириллицу (на PostgreSQL прода группировка полная)
    user = await make_user(session)
    for query in ["Queen", "queen", "QUEEN", "Muse"]:
        await log_search_query(session, user.id, query)

    top = await popular_queries(session)

    assert len(top) == 2
    assert top[0].lower() == "queen"  # 3 раза против 1


async def test_popular_respects_limit(session):
    user = await make_user(session)
    for i in range(15):
        await log_search_query(session, user.id, f"запрос {i}")

    top = await popular_queries(session)

    assert len(top) == 10

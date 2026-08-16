"""Выборка кандидатов ночного ремонта каталога.

🔴 Замер 16.08 показал, что очередь не двигалась: условие «заведён до переезда на
нового бота» истинно навсегда (восстановление сохраняет `created_at`), а
неудачная попытка не оставляла следа вовсе. За первую же ночь 11 треков из 100
оказались уже живыми и 17 не нашлись — и завтра пришли бы те же самые.
"""
from datetime import datetime, timedelta

import pytest

from app.cli.repair_catalog import BOT_SWAP, RECHECK_AFTER_DAYS, _pick
from app.db.models import Track


def _t(id_, *, file_id="abc", created=None, checked=None):
    return Track(
        id=id_,
        artist=f"Артист {id_}",
        title=f"Трек {id_}",
        duration=180,
        tg_file_id=file_id,
        created_at=created or (BOT_SWAP - timedelta(days=1)),
        repair_checked_at=checked,
    )


@pytest.mark.asyncio
async def test_untouched_tracks_are_picked(session):
    session.add(_t(1))
    await session.commit()

    assert [t.id for t in await _pick(session, 10, popular=False)] == [1]


@pytest.mark.asyncio
async def test_recently_touched_tracks_are_skipped(session):
    """Главная починка: тот, кем занимались вчера, сегодня в очередь не идёт."""
    session.add(_t(1, checked=datetime.utcnow() - timedelta(days=1)))
    await session.commit()

    assert await _pick(session, 10, popular=False) == []


@pytest.mark.asyncio
async def test_old_attempt_is_retried(session):
    """«Не нашлось в источниках» — состояние временное: каталоги пополняются,
    и через окно трек надо попробовать снова."""
    session.add(_t(1, checked=datetime.utcnow() - timedelta(days=RECHECK_AFTER_DAYS + 1)))
    await session.commit()

    assert [t.id for t in await _pick(session, 10, popular=False)] == [1]


@pytest.mark.asyncio
async def test_dead_id_is_picked_even_if_recent_track(session):
    """Погашенный id — повод чинить независимо от даты заведения."""
    session.add(_t(1, file_id=None, created=datetime.utcnow()))
    await session.commit()

    assert [t.id for t in await _pick(session, 10, popular=False)] == [1]


@pytest.mark.asyncio
async def test_healthy_recent_track_is_not_a_candidate(session):
    """Трек, заминченный нынешним ботом, чинить незачем."""
    session.add(_t(1, created=datetime.utcnow()))
    await session.commit()

    assert await _pick(session, 10, popular=False) == []


@pytest.mark.asyncio
async def test_limit_is_respected(session):
    session.add_all([_t(i) for i in range(1, 8)])
    await session.commit()

    assert len(await _pick(session, 3, popular=False)) == 3

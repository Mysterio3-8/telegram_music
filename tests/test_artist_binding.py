import json

import pytest

from app.db.models import Artist, Track
from app.services.artist_binding import bind_tracks, resolve_artist_id, unbound_report


@pytest.mark.asyncio
async def test_resolve_by_normalized_name(session):
    artist = Artist(name="Big Baby Tape", normalized_name="big baby tape")
    session.add(artist)
    await session.commit()
    assert await resolve_artist_id(session, "  Big Baby Tape ") == artist.id
    assert await resolve_artist_id(session, "кто-то другой") is None
    assert await resolve_artist_id(session, "  ") is None


@pytest.mark.asyncio
async def test_bind_tracks_by_name_and_alias(session):
    kizaru = Artist(
        name="Kizaru", normalized_name="kizaru",
        aliases=json.dumps(["Кизару"], ensure_ascii=False),
    )
    session.add(kizaru)
    session.add_all([
        Track(title="A", artist="KIZARU", duration=100),
        Track(title="B", artist="Кизару ", duration=100),  # алиас
        Track(title="C", artist="Неизвестный", duration=100),
    ])
    await session.commit()

    bound = await bind_tracks(session)
    assert bound == 2

    from sqlalchemy import select
    rows = (await session.execute(select(Track.title, Track.artist_id))).all()
    by_title = dict(rows)
    assert by_title["A"] == kizaru.id and by_title["B"] == kizaru.id
    assert by_title["C"] is None

    # Повторный бэкфилл ничего не делает
    assert await bind_tracks(session) == 0

    report = await unbound_report(session)
    assert len(report) == 1
    assert report[0].name == "Неизвестный" and report[0].track_count == 1

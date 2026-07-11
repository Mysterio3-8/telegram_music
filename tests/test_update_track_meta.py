from app.db.models import Track
from app.services.library import update_track_meta


async def make_track(session, meta_synced: bool = True) -> Track:
    track = Track(title="Old Title", artist="Old Artist", duration=200, meta_synced=meta_synced)
    session.add(track)
    await session.commit()
    return track


async def test_update_changes_fields_and_resets_meta_synced(session):
    track = await make_track(session)

    updated = await update_track_meta(session, track.id, "New Title", "New Artist")

    assert updated.title == "New Title"
    assert updated.artist == "New Artist"
    assert updated.meta_synced is False  # файл будет перетегирован при следующей выдаче


async def test_update_keeps_field_when_none(session):
    track = await make_track(session)

    updated = await update_track_meta(session, track.id, None, "New Artist")

    assert updated.title == "Old Title"
    assert updated.artist == "New Artist"
    assert updated.meta_synced is False


async def test_no_change_keeps_meta_synced(session):
    track = await make_track(session)

    updated = await update_track_meta(session, track.id, "Old Title", None)

    assert updated.meta_synced is True


async def test_update_missing_track_returns_none(session):
    assert await update_track_meta(session, 999, "T", "A") is None

from app.db.models import YoutubeImport
from app.services.youtube.downloader import VideoEntry
from app.services.youtube.sources import (
    add_source,
    delete_source,
    pending_import_ids,
    register_found_videos,
    requeue_stuck,
    set_source_status,
    sources_due_for_check,
)


async def test_register_videos_dedupes_by_source_and_video(session):
    source = await add_source(session, "https://youtube.com/@ch")
    videos = [VideoEntry("aaaaaaaaaaa", "A - 1"), VideoEntry("bbbbbbbbbbb", "B - 2")]

    added_first = await register_found_videos(session, source.id, videos)
    added_second = await register_found_videos(session, source.id, videos + [VideoEntry("ccccccccccc", "C - 3")])

    assert added_first == 2
    assert added_second == 1  # только новый ccccccccccc
    pending = await pending_import_ids(session, source.id)
    assert len(pending) == 3


async def test_register_updates_found_and_last_checked(session):
    source = await add_source(session, "https://youtube.com/@ch")

    await register_found_videos(session, source.id, [VideoEntry("aaaaaaaaaaa", "x")])

    refreshed = await session.get(type(source), source.id)
    assert refreshed.found_count == 1
    assert refreshed.imported_count == 0
    assert refreshed.last_checked_at is not None


async def test_requeue_stuck_resets_downloading_and_processing(session):
    source = await add_source(session, "https://youtube.com/@ch")
    session.add_all(
        [
            YoutubeImport(source_id=source.id, video_id="v1", status="downloading"),
            YoutubeImport(source_id=source.id, video_id="v2", status="processing"),
            YoutubeImport(source_id=source.id, video_id="v3", status="imported"),
        ]
    )
    await session.commit()

    requeued = await requeue_stuck(session)

    assert len(requeued) == 2
    pending = await pending_import_ids(session, source.id)
    assert len(pending) == 2


async def test_delete_source_removes_queue(session):
    source = await add_source(session, "https://youtube.com/@ch")
    await register_found_videos(session, source.id, [VideoEntry("aaaaaaaaaaa", "x")])

    await delete_source(session, source.id)

    assert await session.get(type(source), source.id) is None
    remaining = (await session.scalars(YoutubeImport.__table__.select())).all()
    assert len(remaining) == 0


async def test_disabled_source_not_due_for_check(session):
    source = await add_source(session, "https://youtube.com/@ch")
    await set_source_status(session, source.id, "disabled")

    due = await sources_due_for_check(session)

    assert source.id not in due


async def test_active_never_checked_is_due(session):
    source = await add_source(session, "https://youtube.com/@ch")

    due = await sources_due_for_check(session)

    assert source.id in due

from app.db.models import Track
from app.services.storage_cleanup import count_reclaimable, reclaim_disk_space
from app.storage.local import LocalStorage


async def test_count_reclaimable_only_counts_synced_tracks_with_archive(session):
    session.add_all(
        [
            # архив + синхронный file_id — можно освободить
            Track(
                title="A", artist="X", duration=100,
                storage_path="local://tracks/1", tg_file_id="f1", meta_synced=True, file_size=1_000_000,
            ),
            # архив, но file_id ещё не подтверждён (meta_synced=False) — трогать нельзя
            Track(
                title="B", artist="X", duration=100,
                storage_path="local://tracks/2", tg_file_id="f2", meta_synced=False, file_size=2_000_000,
            ),
            # архив, но file_id вообще отсутствует — единственная копия, трогать нельзя
            Track(title="C", artist="X", duration=100, storage_path="local://tracks/3", file_size=3_000_000),
            # уже без архива — не считается
            Track(title="D", artist="X", duration=100, tg_file_id="f4", meta_synced=True),
        ]
    )
    await session.commit()

    count, total_bytes = await count_reclaimable(session)

    assert count == 1
    assert total_bytes == 1_000_000


async def test_reclaim_deletes_files_and_clears_storage_path(session, tmp_path):
    storage = LocalStorage(str(tmp_path))
    storage.save("tracks/1", b"audio-bytes")
    track = Track(
        title="A", artist="X", duration=100,
        storage_path="local://tracks/1", tg_file_id="f1", meta_synced=True, file_size=11,
    )
    session.add(track)
    await session.commit()

    deleted = await reclaim_disk_space(session, storage)

    assert deleted == 1
    assert storage.exists("tracks/1") is False
    await session.refresh(track)
    assert track.storage_path is None
    assert track.tg_file_id == "f1"  # ссылка на Telegram не пострадала


async def test_reclaim_ignores_tracks_without_synced_file_id(session, tmp_path):
    storage = LocalStorage(str(tmp_path))
    storage.save("tracks/1", b"audio-bytes")
    track = Track(title="A", artist="X", duration=100, storage_path="local://tracks/1", file_size=11)
    session.add(track)
    await session.commit()

    deleted = await reclaim_disk_space(session, storage)

    assert deleted == 0
    assert storage.exists("tracks/1") is True
    await session.refresh(track)
    assert track.storage_path == "local://tracks/1"


async def test_reclaim_returns_zero_when_nothing_to_clean(session, tmp_path):
    storage = LocalStorage(str(tmp_path))

    deleted = await reclaim_disk_space(session, storage)

    assert deleted == 0

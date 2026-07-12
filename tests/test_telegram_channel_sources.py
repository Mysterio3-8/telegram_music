from app.db.models import TelegramChannelImport
from app.services.telegram_channel.scanner import AudioMessageRef
from app.services.telegram_channel.sources import (
    add_source,
    delete_source,
    pending_import_ids,
    register_found_messages,
    requeue_stuck,
    set_source_status,
    sources_due_for_check,
)


def ref(message_id: int, title: str = "x") -> AudioMessageRef:
    return AudioMessageRef(message_id=message_id, posted_title=title, posted_performer="Ch", caption="")


async def test_register_messages_dedupes_by_source_and_message(session):
    source = await add_source(session, "@mychannel")
    refs = [ref(1), ref(2)]

    added_first = await register_found_messages(session, source.id, refs)
    added_second = await register_found_messages(session, source.id, refs + [ref(3)])

    assert added_first == 2
    assert added_second == 1  # только новое сообщение id=3
    pending = await pending_import_ids(session, source.id)
    assert len(pending) == 3


async def test_register_updates_found_and_last_message_id(session):
    source = await add_source(session, "@mychannel")

    await register_found_messages(session, source.id, [ref(5), ref(2)])

    refreshed = await session.get(type(source), source.id)
    assert refreshed.found_count == 2
    assert refreshed.imported_count == 0
    assert refreshed.last_checked_at is not None
    assert refreshed.last_message_id == 5  # продвинулся до максимального id


async def test_second_scan_only_registers_newer_than_last_message_id(session):
    source = await add_source(session, "@mychannel")
    await register_found_messages(session, source.id, [ref(1), ref(2)])

    # имитация нового скана: сканер сам бы запросил min_id=last_message_id,
    # здесь просто проверяем, что уже виденные id не задваиваются при повторной регистрации
    added = await register_found_messages(session, source.id, [ref(2), ref(3)])

    assert added == 1
    pending = await pending_import_ids(session, source.id)
    assert len(pending) == 3


async def test_requeue_stuck_resets_downloading_and_processing(session):
    source = await add_source(session, "@mychannel")
    session.add_all(
        [
            TelegramChannelImport(source_id=source.id, message_id=1, status="downloading"),
            TelegramChannelImport(source_id=source.id, message_id=2, status="processing"),
            TelegramChannelImport(source_id=source.id, message_id=3, status="imported"),
        ]
    )
    await session.commit()

    requeued = await requeue_stuck(session)

    assert len(requeued) == 2
    pending = await pending_import_ids(session, source.id)
    assert len(pending) == 2


async def test_delete_source_removes_queue(session):
    source = await add_source(session, "@mychannel")
    await register_found_messages(session, source.id, [ref(1)])

    await delete_source(session, source.id)

    assert await session.get(type(source), source.id) is None
    remaining = (await session.scalars(TelegramChannelImport.__table__.select())).all()
    assert len(remaining) == 0


async def test_disabled_source_not_due_for_check(session):
    source = await add_source(session, "@mychannel")
    await set_source_status(session, source.id, "disabled")

    due = await sources_due_for_check(session)

    assert source.id not in due


async def test_active_never_checked_is_due(session):
    source = await add_source(session, "@mychannel")

    due = await sources_due_for_check(session)

    assert source.id in due

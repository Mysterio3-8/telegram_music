from app.db.models import Track
from app.services.moderation import (
    count_pending,
    initial_status,
    is_flagged,
    pending_tracks,
    set_status,
)
from app.services.recommendations import build_mix
from app.services.search import search_tracks


def test_is_flagged_catches_stopwords():
    assert is_flagged("Гимн террористов", "X")
    assert is_flagged("X", "ИГИЛ")
    assert is_flagged("Suicide note", "Band")


def test_is_flagged_ignores_clean_titles():
    assert not is_flagged("Розовое вино", "Элджей")
    assert not is_flagged("Fake ID", "kizaru")
    # «террор» как часть другого слова не ловим (границы слов)
    assert not is_flagged("Territory", "Band")


def test_initial_status():
    assert initial_status("Розовое вино", "Элджей") == "approved"
    assert initial_status("Теракт", "X") == "pending"


async def _track(session, title, artist="A", status="approved") -> Track:
    track = Track(title=title, artist=artist, duration=200, moderation_status=status)
    session.add(track)
    await session.commit()
    return track


async def test_pending_flow(session):
    await _track(session, "Обычный трек", status="approved")
    flagged = await _track(session, "Экстремизм", status="pending")
    assert await count_pending(session) == 1
    queue = await pending_tracks(session)
    assert [t.id for t in queue] == [flagged.id]

    assert await set_status(session, flagged.id, "approved") is True
    assert await count_pending(session) == 0


async def test_search_excludes_pending(session):
    await _track(session, "Хит", artist="Певец", status="approved")
    await _track(session, "Хит запретный", artist="Певец", status="pending")
    tracks, total = await search_tracks(session, "Хит", page=1)
    titles = [t.title for t in tracks]
    assert "Хит" in titles
    assert "Хит запретный" not in titles
    assert total == 1


async def test_mix_excludes_pending(session):
    await _track(session, "Ок", status="approved")
    await _track(session, "Скрыт", status="pending")
    mix = await build_mix(session)
    titles = [t.title for t in mix]
    assert "Ок" in titles
    assert "Скрыт" not in titles

from app.db.models import Instrumental
from app.services.instrumentals import create_admin_instrumental, find_duplicate_instrumental
from app.services.uploads import AudioMeta


def make_meta(duration=180, file_id="tg_file_1") -> AudioMeta:
    return AudioMeta(file_id=file_id, file_name="a.mp3", mime_type="audio/mpeg", file_size=1000, duration=duration)


async def test_create_admin_instrumental_sets_source_and_file_id(session):
    instrumental = await create_admin_instrumental(session, make_meta(), "Captain", "Miyagi")

    assert instrumental.title == "Captain"
    assert instrumental.artist == "Miyagi"
    assert instrumental.tg_file_id == "tg_file_1"
    assert instrumental.source == "admin_manual"


async def test_find_duplicate_instrumental_matches_metadata(session):
    session.add(Instrumental(title="Captain", artist="Miyagi", duration=180, source="import"))
    await session.commit()

    found = await find_duplicate_instrumental(session, "captain", "miyagi", 181)

    assert found is not None
    assert found.title == "Captain"


async def test_find_duplicate_instrumental_ignores_matching_track(session):
    """Полноценный трек с тем же названием/исполнителем не считается дубликатом минуса (TZ §9)."""
    from app.db.models import Track

    session.add(Track(title="Captain", artist="Miyagi", duration=180))
    await session.commit()

    found = await find_duplicate_instrumental(session, "Captain", "Miyagi", 180)

    assert found is None


async def test_find_duplicate_instrumental_none_when_not_found(session):
    found = await find_duplicate_instrumental(session, "Nope", "Nobody", 100)

    assert found is None

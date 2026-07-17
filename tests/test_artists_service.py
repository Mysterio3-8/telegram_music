from app.db.models import Track
from app.services.artists import artist_tracks, list_artists


def make_track(title, artist) -> Track:
    return Track(title=title, artist=artist, duration=180)


async def test_list_artists_dedups_case_and_spaces(session):
    session.add_all(
        [
            make_track("t1", "Miyagi"),
            make_track("t2", "miyagi"),
            make_track("t3", " MIYAGI "),
            make_track("t4", "Скриптонит"),
        ]
    )
    await session.commit()

    artists = await list_artists(session)

    assert len(artists) == 2
    assert artists[0].track_count == 3
    assert artists[0].name.lower().strip() == "miyagi"


async def test_artist_tracks_matches_normalized(session):
    session.add_all([make_track("t1", "Miyagi"), make_track("t2", " miyagi"), make_track("t3", "Другой")])
    await session.commit()

    tracks = await artist_tracks(session, "MIYAGI ")

    assert len(tracks) == 2


async def test_list_artists_skips_empty(session):
    session.add_all([make_track("t1", ""), make_track("t2", "Артист")])
    await session.commit()

    artists = await list_artists(session)

    assert [a.name for a in artists] == ["Артист"]

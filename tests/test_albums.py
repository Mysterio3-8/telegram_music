"""Альбомы целиком (16.09): поиск, фильтр перезаливов, полный список треков.

Данные повторяют реальные ответы SoundCloud из прогона на проде 16.09.
"""
from app.services import albums
from app.services.albums import AlbumCandidate, album_tracks, parse_album, rank_albums, search_albums


def _item(album_id, title, user, count, likes=0, verified=False, kind="album"):
    return {
        "id": album_id,
        "title": title,
        "permalink_url": f"https://soundcloud.com/x/sets/{album_id}",
        "track_count": count,
        "likes_count": likes,
        "set_type": kind,
        "artwork_url": "https://i1.sndcdn.com/artworks-abc-large.jpg",
        "user": {"username": user, "verified": verified},
    }


def _albums(query, items, limit=5):
    return rank_albums(query, [parse_album(item) for item in items], limit)


def test_official_first_duplicates_collapsed_junk_hidden():
    items = [
        _item(1, "СКРИПТОНИТ - 2004 (Album 24.12.2019)", "M U S I C", 24, likes=38),
        _item(2, "2004", "Cкриптoнит", 24, likes=11466, verified=True),  # латинские C и o
        _item(3, "Скриптонит - 2004", "COLDDEADBABY", 46, likes=2),
        _item(4, "Скриптонит 2004", "Mark Левин", 0),  # пустой
        _item(5, "NEW SCHOOL", "minekeed", 5, likes=26),  # посторонний
    ]
    found = _albums("скриптонит 2004", items)
    assert [a.id for a in found] == [2]  # три копии «2004» схлопнулись в официальную
    assert found[0].official and found[0].title == "2004" and found[0].track_count == 24
    assert found[0].cover_url.endswith("-t500x500.jpg")


def test_versions_hidden_unless_asked():
    items = [
        _item(10, "BORN TO TRAP", "kizaru", 18, likes=24924, verified=True),
        _item(11, "Kizaru - Born To Trap (альбом)[замедленный + пространство]", "slow", 18, likes=377),
    ]
    assert [a.id for a in _albums("kizaru born to trap", items)] == [10]
    slowed = [_item(12, "Dragonborn (slowed + reverb)", "fan", 20)]
    assert _albums("dragonborn", slowed) == []
    assert [a.id for a in _albums("dragonborn slowed", slowed)] == [12]


def test_single_and_unofficial_hidden():
    items = [
        _item(20, "Май", "MACAN", 1, verified=True),  # сингл, не альбом
        _item(21, "BIG BABY TAPE / DRAGONBORN UNOFFICIAL", "larikidd", 20),
        _item(22, "Dragonborn", "Big Baby Tape", 23, likes=15241, verified=True),
    ]
    assert [a.id for a in _albums("macan май", items)] == []
    assert [a.id for a in _albums("big baby tape dragonborn", items)] == [22]


def test_official_only_by_verification_or_title_match():
    """Аккаунт без тире в названии не становится «официальным» автоматически."""
    fan = parse_album(_item(30, "Скриптонит 2004", "Mark Левин", 10))
    assert fan.official is False
    self_upload = parse_album(_item(31, "kizaru - BORN TO TRAP", "kizaru", 18))
    assert self_upload.official is True and self_upload.title == "BORN TO TRAP"


def test_relevant_reupload_beats_irrelevant_official():
    items = [
        _item(40, "PEEKABOO", "Big Baby Tape", 15, likes=11558, verified=True),
        _item(41, "Big Baby Tape - Dragonborn (Album)", "M U S I C", 23, likes=40),
    ]
    found = _albums("dragonborn", items)
    assert found[0].id == 41


def test_search_albums_uses_api(monkeypatch):
    calls = []

    def fake_get(path, params=None):
        calls.append((path, params))
        return {"collection": [_item(50, "I AM", "MACAN", 21, likes=525, verified=True)]}

    monkeypatch.setattr("app.services.soundcloud_api.api_get", fake_get)
    found = search_albums("macan i am")
    assert [a.title for a in found] == ["I AM"]
    assert calls[0][0] == "/search/albums" and calls[0][1]["q"] == "macan i am"
    assert search_albums("   ") == []


def _track(track_id, title, full=True):
    if not full:
        return {"id": track_id}  # заглушка: так API отдаёт треки с шестого
    return {
        "id": track_id,
        "title": title,
        "permalink_url": f"https://soundcloud.com/a/{track_id}",
        "duration": 180000,
        "user": {"username": "Скриптонит"},
        "playback_count": 1000,
    }


def test_album_tracks_hydrates_stubs_in_order(monkeypatch):
    albums._cache.clear()
    playlist = {
        "artwork_url": "https://i1.sndcdn.com/album.jpg",
        "user": {"username": "Скриптонит"},
        "tracks": [_track(i, f"Трек {i}") for i in range(1, 6)]
        + [_track(i, "", full=False) for i in range(6, 25)],
    }
    requests = []

    def fake_get(path, params=None):
        requests.append(path)
        if path.startswith("/playlists/"):
            return playlist
        ids = [int(x) for x in params["ids"].split(",")]
        # API возвращает в своём порядке — сборка обязана восстановить порядок альбома
        return [_track(i, f"Трек {i}") for i in reversed(ids) if i != 13]  # 13-й удалён

    monkeypatch.setattr("app.services.soundcloud_api.api_get", fake_get)
    tracks = album_tracks(777)
    titles = [c.title for c in tracks]
    assert len(tracks) == 23  # 24 минус удалённый
    assert titles[:6] == ["Трек 1", "Трек 2", "Трек 3", "Трек 4", "Трек 5", "Трек 6"]
    assert "Трек 13" not in titles and titles[-1] == "Трек 24"
    assert requests.count("/tracks") == 1  # 19 заглушек — один запрос дозагрузки

    album_tracks(777)
    assert len(requests) == 2  # второй раз — из кэша, без сети


def test_album_tracks_empty_when_api_down(monkeypatch):
    albums._cache.clear()
    monkeypatch.setattr("app.services.soundcloud_api.api_get", lambda path, params=None: None)
    assert album_tracks(1) == []


def test_album_candidate_roundtrip():
    album = parse_album(_item(60, "12", "MACAN", 12, verified=True))
    assert AlbumCandidate(**album.as_dict()) == album

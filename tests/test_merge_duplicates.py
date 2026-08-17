"""Слияние дубликатов: связи людей обязаны пережить операцию.

Удалять лишние строки напрямую нельзя — они лежат в чужих библиотеках и
плейлистах, и человек молча потерял бы трек из подборки. Восстанавливать было бы
нечего: запись удаляется вместе с названием. Здесь это и проверяется.
"""
import pytest

from app.cli.merge_duplicates import _build_groups, _group_keys, _keeper, _merge_group
from app.db.models import (
    Lyrics,
    Playlist,
    PlaylistTrack,
    Track,
    TrackEvent,
    User,
    UserLibrary,
)
from app.services.search_index import build_search_index


def _t(id_, artist="yarik", title="Зеркало", duration=152, file_id="live", url=None):
    return Track(
        id=id_, artist=artist, title=title, duration=duration,
        tg_file_id=file_id, source_url=url,
        search_index=build_search_index(artist, title),
    )


# --- кого оставляем ----------------------------------------------------------------


def test_track_with_file_wins():
    """Слить в пустышку — потерять трек, даже если её слушали чаще."""
    dead = _t(1, file_id=None)
    live = _t(2, file_id="live")
    assert _keeper([dead, live], {1: 100, 2: 0}) is live


def test_most_played_wins_among_alive():
    quiet, popular = _t(1), _t(2)
    assert _keeper([quiet, popular], {1: 0, 2: 50}) is popular


def test_oldest_wins_when_equal():
    """У старого больше шансов быть привязанным в чужих плейлистах."""
    old, new = _t(1), _t(9)
    assert _keeper([new, old], {}) is old


# --- что считаем одной записью -----------------------------------------------------


def test_same_source_url_is_one_group():
    a = _t(1, url="https://sc/x")
    b = _t(2, artist="другой", title="другое", url="https://sc/x")
    assert len(_build_groups([a, b])) == 1


def test_different_duration_is_not_one_group():
    assert _build_groups([_t(1, duration=261), _t(2, duration=218)]) == []


def test_track_without_index_and_url_is_skipped():
    bare = Track(id=1, artist="A", title="B", duration=100)
    assert _group_keys(bare) == []


def test_copy_without_url_joins_its_group():
    """🔴 Живой случай «КИШЛАК — Угу»: самая старая копия ссылки не имеет, три
    остальные имеют. Группировка по одному ключу оставила бы старую висеть
    отдельным дубликатом."""
    old = _t(1, url=None)
    a = _t(2, url="https://sc/ugu")
    b = _t(3, url="https://sc/ugu")

    groups = _build_groups([old, a, b])
    assert len(groups) == 1 and len(groups[0]) == 3


def test_unrelated_tracks_stay_apart():
    a = _t(1, artist="Хаски", title="Панелька", duration=200)
    b = _t(2, artist="Кизару", title="Яд", duration=150)
    assert _build_groups([a, b]) == []


# --- перенос связей ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_library_and_playlist_survive_merge(session):
    keeper, loser = _t(1), _t(2)
    user = User(telegram_id=555)
    session.add_all([keeper, loser, user])
    await session.flush()
    playlist = Playlist(user_id=user.id, title="Моя подборка")
    session.add(playlist)
    await session.flush()
    # человек добавил себе ИМЕННО дубликат
    session.add_all([
        UserLibrary(user_id=user.id, track_id=loser.id),
        PlaylistTrack(playlist_id=playlist.id, track_id=loser.id, position=1),
        TrackEvent(user_id=user.id, track_id=loser.id, event="listen"),
    ])
    await session.commit()

    await _merge_group(session, keeper, [loser])

    lib = (await session.scalars(select_lib(user.id))).all()
    assert [row for row in lib] == [keeper.id]
    pls = (await session.scalars(select_pl(playlist.id))).all()
    assert [row for row in pls] == [keeper.id]
    assert await session.get(Track, loser.id) is None


def select_lib(user_id):
    from sqlalchemy import select

    return select(UserLibrary.track_id).where(UserLibrary.user_id == user_id)


def select_pl(playlist_id):
    from sqlalchemy import select

    return select(PlaylistTrack.track_id).where(PlaylistTrack.playlist_id == playlist_id)


@pytest.mark.asyncio
async def test_no_duplicate_row_when_user_has_both(session):
    """У человека в библиотеке лежат обе копии — после слияния должна остаться одна."""
    keeper, loser = _t(1), _t(2)
    user = User(telegram_id=556)
    session.add_all([keeper, loser, user])
    await session.flush()
    session.add_all([
        UserLibrary(user_id=user.id, track_id=keeper.id),
        UserLibrary(user_id=user.id, track_id=loser.id),
    ])
    await session.commit()

    await _merge_group(session, keeper, [loser])

    rows = (await session.scalars(select_lib(user.id))).all()
    assert list(rows) == [keeper.id]


@pytest.mark.asyncio
async def test_useful_fields_move_to_keeper(session):
    """Обидно потерять обложку только потому, что она досталась дубликату."""
    keeper = _t(1)
    loser = _t(2, url="https://sc/x")
    loser.cover_url = "https://img/cover.jpg"
    session.add_all([keeper, loser])
    await session.commit()

    await _merge_group(session, keeper, [loser])

    assert keeper.source_url == "https://sc/x"
    assert keeper.cover_url == "https://img/cover.jpg"


@pytest.mark.asyncio
async def test_existing_lyrics_are_not_overwritten(session):
    keeper, loser = _t(1), _t(2)
    session.add_all([keeper, loser])
    await session.flush()
    session.add_all([
        Lyrics(track_id=keeper.id, text="свой текст", source="manual"),
        Lyrics(track_id=loser.id, text="чужой текст", source="lrclib"),
    ])
    await session.commit()

    await _merge_group(session, keeper, [loser])

    kept = await session.get(Lyrics, keeper.id)
    assert kept.text == "свой текст"

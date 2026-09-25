"""Infinity Mix: бесконечная лента без минусов и без повторов (владелец 22.09).

Жалоба была буквальная: «Хочу послушать микс, а включается микс только из
минусов, а надо чтобы рандомные треки, абсолютно рандомные, даже которых нет в
базе, без повторов».
"""
import pytest

from app.db.models import MixHistory, Track, User
from app.services import infinity_mix
from app.services.track_lookup.ranking import Candidate


async def _user(session) -> User:
    user = User(telegram_id=555, first_name="T")
    session.add(user)
    await session.commit()
    return user


async def _tracks(session, count: int, prefix: str = "T") -> list[Track]:
    rows = [
        Track(title=f"{prefix}{i}", artist=f"A{i}", duration=200, tg_file_id=f"file-{prefix}{i}")
        for i in range(count)
    ]
    session.add_all(rows)
    await session.commit()
    return rows


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Источник в тестах не дёргаем — его ответ подменяют сами тесты."""

    async def empty(_seed):
        return []

    monkeypatch.setattr("app.services.search_cache.search_with_cache", empty)
    return empty


async def test_catalog_part_skips_tracks_shown_this_week(session):
    user = await _user(session)
    rows = await _tracks(session, 3)
    session.add(MixHistory(user_id=user.id, track_id=rows[0].id))
    await session.commit()

    picked = await infinity_mix._catalog_part(session, user.id, limit=10)
    assert rows[0].id not in {t.id for t in picked}
    assert len(picked) == 2


async def test_shown_tracks_are_remembered(session):
    user = await _user(session)
    await _tracks(session, 4)
    catalog, _live = await infinity_mix.build_infinity_mix(session, user.id, size=4)
    remembered = set((await session.scalars(MixHistory.__table__.select().with_only_columns(MixHistory.track_id))).all())
    assert {t.id for t in catalog} <= remembered


async def test_tracks_without_file_id_are_not_offered(session):
    """Трек без file_id — это ожидание вместо музыки: в ленту он не попадает."""
    user = await _user(session)
    session.add(Track(title="No file", artist="A", duration=200, tg_file_id=None, storage_path=None))
    await session.commit()
    picked = await infinity_mix._catalog_part(session, user.id, limit=10)
    assert picked == []


async def test_live_part_drops_what_is_already_in_catalog(session, monkeypatch):
    """Живой кандидат, совпавший с треком каталога, из ленты убирается —
    иначе одна и та же песня прозвучала бы дважды подряд."""
    user = await _user(session)
    session.add(Track(title="Fendi", artist="Kizaru", duration=200, tg_file_id="f"))
    await session.commit()

    async def one(_seed):
        return [
            Candidate(
                source="soundcloud",
                url="https://soundcloud.com/kizaru/fendi",
                title="Fendi",
                duration=200,
                artist="Kizaru",
            )
        ]

    monkeypatch.setattr("app.services.search_cache.search_with_cache", one)
    _catalog, live = await infinity_mix.build_infinity_mix(session, user.id, size=6)
    assert live == []


async def test_empty_catalog_still_returns_live(session, monkeypatch):
    user = await _user(session)

    async def one(_seed):
        return [
            Candidate(
                source="soundcloud",
                url="https://soundcloud.com/x/y",
                title="Y",
                duration=200,
                artist="X",
            )
        ]

    monkeypatch.setattr("app.services.search_cache.search_with_cache", one)
    catalog, live = await infinity_mix.build_infinity_mix(session, user.id, size=6)
    assert catalog == []
    assert live and live[0].title == "Y"


async def test_go_plus_previews_are_not_in_mix(session, monkeypatch):
    """Прогон 25.09: «New Choppa» играл 0:30 — превью Go+ в ленте."""
    user = await _user(session)

    async def mixed(_seed):
        return [
            Candidate(source="soundcloud", url="https://sc/p", title="Preview", duration=183,
                      artist="X", snippet=True),
            Candidate(source="soundcloud", url="https://sc/f", title="Full", duration=200, artist="X"),
        ]

    monkeypatch.setattr("app.services.search_cache.search_with_cache", mixed)
    _catalog, live = await infinity_mix.build_infinity_mix(session, user.id, size=6)
    assert [c.title for c in live] == ["Full"]

"""Дедуп по «исполнитель — название» на кириллице.

🔴 Замер 16.08. `find_duplicate` сравнивал `lower(Track.title)` с уже понижённой
в Питоне строкой, а SQLite `lower()` понижает ТОЛЬКО ASCII. Для кириллицы
сравнение не совпадало никогда: Питон давал «зеркало», база оставалась с
«Зеркало». Дедуп при этом не падал, а молча возвращал None — и каждый повторный
импорт заводил ещё одну копию.

На проде это дало 140 пар с дублями (у 61 кириллица в названии), в том числе
шесть копий «yarik — Зеркало» с одной и той же ссылкой источника.
"""
import pytest

from app.db.models import Track
from app.services.search_index import build_search_index
from app.services.uploads import find_duplicate


def _t(id_, artist, title, duration=152, with_index=True):
    return Track(
        id=id_,
        artist=artist,
        title=title,
        duration=duration,
        search_index=build_search_index(artist, title) if with_index else None,
    )


@pytest.mark.asyncio
async def test_cyrillic_duplicate_is_found(session):
    """Тот самый случай: до починки здесь был None и заводилась копия."""
    session.add(_t(1, "yarik", "Зеркало"))
    await session.commit()

    found = await find_duplicate(session, "Зеркало", "yarik", 152)
    assert found is not None and found.id == 1


@pytest.mark.asyncio
async def test_cyrillic_duplicate_found_regardless_of_case(session):
    session.add(_t(1, "КИШЛАК", "Угу", duration=190))
    await session.commit()

    assert (await find_duplicate(session, "угу", "кишлак", 190)) is not None


@pytest.mark.asyncio
async def test_latin_duplicate_still_found(session):
    """Латиница работала и раньше — проверяем, что не сломали."""
    session.add(_t(1, "Big Baby Tape", "Dayang", duration=180))
    await session.commit()

    assert (await find_duplicate(session, "dayang", "big baby tape", 180)) is not None


@pytest.mark.asyncio
async def test_legacy_row_without_index_still_matched(session):
    """Фолбэк: у одной строки на проде search_index пуст, и её тоже надо ловить."""
    session.add(_t(1, "Kizaru", "Fake ID", duration=200, with_index=False))
    await session.commit()

    assert (await find_duplicate(session, "fake id", "kizaru", 200)) is not None


@pytest.mark.asyncio
async def test_different_artist_is_not_a_duplicate(session):
    """«Кизару — Зеркало» и «yarik — Зеркало» — разные записи, склеивать нельзя."""
    session.add(_t(1, "Кизару", "Зеркало"))
    await session.commit()

    assert (await find_duplicate(session, "Зеркало", "yarik", 152)) is None


@pytest.mark.asyncio
async def test_different_duration_is_not_a_duplicate(session):
    """Разная длительность — разные записи (живой пример: четыре «Беззаботный»
    Александра Маршала на 261, 218, 215 и 233 секунды)."""
    session.add(_t(1, "Александр Маршал", "Беззаботный", duration=261))
    await session.commit()

    assert (await find_duplicate(session, "Беззаботный", "Александр Маршал", 218)) is None


# --- ссылка источника проверяется и при вставке ------------------------------------


@pytest.mark.asyncio
async def test_same_source_url_is_a_duplicate_even_if_metadata_differs(session):
    """Один и тот же трек у источника подписан по-разному в выдаче и в файле.
    Ссылка — точный ключ, и проверять её надо в момент вставки: между проверкой
    перед скачиванием и самой вставкой проходит восемь секунд, а 11.08 очередь
    задач пошла разом, и в это окно влезали дубликаты."""
    from app.services.catalog_import import find_existing_track

    track = _t(1, "Кизару", "Зеркало")
    track.source_url = "https://soundcloud.com/yarosoav/kizaru-zerkalo"
    session.add(track)
    await session.commit()

    found = await find_existing_track(
        session, None, "Зеркало (Official Audio)", "yarik", 152,
        source_url="https://soundcloud.com/yarosoav/kizaru-zerkalo",
    )
    assert found is not None and found.id == 1


@pytest.mark.asyncio
async def test_other_source_url_is_not_a_duplicate(session):
    from app.services.catalog_import import find_existing_track

    track = _t(1, "Кизару", "Зеркало")
    track.source_url = "https://soundcloud.com/a/one"
    session.add(track)
    await session.commit()

    assert await find_existing_track(
        session, None, "Совсем другое", "Другой", 300,
        source_url="https://soundcloud.com/b/two",
    ) is None

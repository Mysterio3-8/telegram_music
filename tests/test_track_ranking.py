"""Порядок треков из нашей базы — жалоба на инлайн-выдачу.

Живой поиск по источникам ранжировался давно, а поиск по собственной базе всё
это время шёл `ORDER BY artist, title`, то есть по алфавиту: по запросу «kizaru»
первым выходил «044ROSE — STOP XANAX ДЭМО ДЛЯ КИЗАРУ», потому что ноль стоит
раньше букв.
"""
import pytest

from app.db.models import Track
from app.services.search import search_tracks
from app.services.track_ranking import rank_tracks, track_relevance


def _t(id_, artist, title, duration=180):
    return Track(id=id_, artist=artist, title=title, duration=duration)


def test_alphabet_no_longer_decides():
    noise = _t(1, "044ROSE", "STOP XANAX ДЭМО ДЛЯ КИЗАРУ")
    wanted = _t(2, "KIZARU", "Яд")

    assert rank_tracks("kizaru", [noise, wanted])[0] is wanted


def test_exact_title_wins_within_one_artist():
    other = _t(1, "Хаски", "Пуля-дура")
    wanted = _t(2, "Хаски", "Панелька")

    assert rank_tracks("хаски панелька", [other, wanted])[0] is wanted


def test_right_artist_beats_similar_title():
    stranger = _t(1, "Вадим Мулерман", "Ты назови её Мариной")
    wanted = _t(2, "MACAN", "Назови её")

    assert rank_tracks("макан назови её", [stranger, wanted])[0] is wanted


def test_nothing_is_dropped():
    """Ранжирование базы, в отличие от живого поиска, ничего не выбрасывает:
    каждая строка уже прошла отбор при импорте, и прятать её от человека
    неправильно."""
    tracks = [_t(1, "A", "раз"), _t(2, "B", "два"), _t(3, "C", "три")]
    assert len(rank_tracks("совершенно чужой запрос", tracks)) == 3


def test_empty_query_keeps_order():
    tracks = [_t(1, "Б", "раз"), _t(2, "А", "два")]
    assert rank_tracks("   ", tracks) == tracks


def test_relevance_is_a_number():
    assert isinstance(track_relevance("хаски", _t(1, "Хаски", "Панелька")), float)


@pytest.mark.asyncio
async def test_search_tracks_returns_ranked_page(session):
    """Сквозная проверка: то, что человек увидит первым на странице выдачи."""
    session.add_all([
        _t(1, "044ROSE", "STOP XANAX ДЭМО ДЛЯ КИЗАРУ"),
        _t(2, "AAA Kizaru cover", "нечто"),
        _t(3, "KIZARU", "Яд"),
    ])
    await session.commit()

    page, total = await search_tracks(session, "kizaru", 1)
    # ⚠️ Две, а не три: у первого трека «КИЗАРУ» кириллицей, а SQLite ilike
    # понижает только ASCII — это давняя известная грабля, на PostgreSQL совпадут
    # все три. Проверяем здесь именно ПОРЯДОК, а не полноту выборки.
    assert total == 2
    assert page[0].artist == "KIZARU"


@pytest.mark.asyncio
async def test_pagination_still_works(session):
    session.add_all([_t(i, f"Артист {i}", f"Трек {i}") for i in range(1, 13)])
    await session.commit()

    first, total = await search_tracks(session, "Трек", 1)
    second, _ = await search_tracks(session, "Трек", 2)
    assert total == 12
    assert len(first) == 5 and len(second) == 5
    # Страницы не пересекаются — срез идёт по одному и тому же порядку
    assert not ({t.id for t in first} & {t.id for t in second})

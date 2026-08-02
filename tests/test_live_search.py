"""Живой поиск: склейка источников, ссылки на кандидатов, полки настроений.

Сеть здесь не трогаем — только чистая логика, которая решает, что человек увидит.
"""
import pytest

from app.services.candidate_ref import decode_ref, encode_ref
from app.services.shelves import interleave
from app.services.track_lookup import _visible_candidates
from app.services.track_lookup.merge import dedup_key, merge_candidates
from app.services.track_lookup.ranking import Candidate

SC = "soundcloud"
YT = "youtube"


def candidate(title, source=SC, artist=None, duration=180, url=None):
    return Candidate(
        source=source,
        url=url or f"https://{source}.test/{title}",
        title=title,
        duration=duration,
        artist=artist,
    )


def test_soundcloud_goes_first_and_whole():
    sc = [candidate("Fake ID"), candidate("AFK")]
    result = merge_candidates(sc, [candidate("Something else", YT)])
    assert [item.title for item in result[:2]] == ["Fake ID", "AFK"]
    assert all(item.source == SC for item in result[:2])


def test_youtube_duplicate_is_dropped():
    sc = [candidate("Fake ID", artist="Kizaru")]
    yt = [candidate("Kizaru - Fake ID", YT)]
    assert merge_candidates(sc, yt) == sc


def test_youtube_unique_is_added():
    sc = [candidate("Fake ID", artist="Kizaru")]
    yt = [candidate("Kizaru - Nirvana", YT)]
    merged = merge_candidates(sc, yt)
    assert len(merged) == 2
    assert merged[1].source == YT


def test_dedup_works_across_translit():
    """«кизару фейк айди» с SoundCloud и «Kizaru - Fake ID» с YouTube — один трек."""
    assert dedup_key(candidate("фейк айди", artist="кизару")) == dedup_key(
        candidate("feyk aydi", artist="kizaru")
    )


def test_dedup_key_empty_candidates_are_not_collapsed():
    """Кандидаты без опознавательных знаков не схлопываем: показать дважды лучше,
    чем потерять — охват важнее чистоты (решение владельца)."""
    blank = [candidate("!!!", artist=None), candidate("???", artist=None)]
    assert dedup_key(blank[0]) == ""
    assert len(merge_candidates([], blank)) == 2


def test_short_track_survives_now_that_lower_bound_is_off():
    """Фристайл на 40 секунд — ровно тот андеграунд, ради которого делался поиск."""
    short = candidate("skit", artist="artist", duration=40)
    assert short in _visible_candidates("artist skit", [short])


def test_hour_long_mix_is_still_cut():
    long_mix = candidate("phonk mix", artist="dj", duration=4000)
    assert _visible_candidates("dj phonk mix", [long_mix]) == []


def test_visible_falls_back_when_ranking_drops_everything():
    """Ранжирование не нашло совпадения с запросом — отдаём то, что вернул
    источник, иначе экзотические названия не находятся вообще."""
    found = candidate("Zzzz Qqqq", artist="Wwww")
    assert _visible_candidates("совершенно другой запрос", [found]) == [found]


def test_ref_round_trip():
    item = candidate("Fake ID", artist="Kizaru")
    assert decode_ref(encode_ref(item)) == item


def test_ref_with_broken_signature_is_rejected():
    ref = encode_ref(candidate("Fake ID"))
    body, _, signature = ref.partition(".")
    assert decode_ref(f"{body}.{'0' * len(signature)}") is None


def test_expired_ref_is_rejected():
    assert decode_ref(encode_ref(candidate("Fake ID"), ttl_seconds=-1)) is None


@pytest.mark.parametrize("ref", ["", "no-dot", "not-base64.deadbeef"])
def test_garbage_ref_is_rejected(ref):
    assert decode_ref(ref) is None


def test_shelf_interleaves_seeds_instead_of_stacking_them():
    """Полка не должна начинаться десятью треками одного сида."""
    first = [candidate("a1"), candidate("a2")]
    second = [candidate("b1"), candidate("b2")]
    assert [item.title for item in interleave([first, second])] == ["a1", "b1", "a2", "b2"]


def test_shelf_drops_duplicates_between_seeds():
    same = candidate("Fake ID", artist="Kizaru")
    other = candidate("Kizaru - Fake ID", YT)
    assert len(interleave([[same], [other]])) == 1


def test_empty_shelf_does_not_crash():
    assert interleave([]) == []


def test_last_soundcloud_attempt_is_always_direct(monkeypatch):
    """Прод 2026-08-02: все семь прокси отвечали Connection refused, и SoundCloud —
    приоритетный источник — молча отдавал ноль. Прямая попытка обязана быть всегда."""
    from app.config import settings
    from app.services.soundcloud import attempt_plan

    monkeypatch.setattr(settings, "proxy_list", "http://a:1,http://b:2")
    plan = attempt_plan()
    assert plan[-1] is False
    assert any(plan[:-1])  # прокси всё ещё пробуем первыми


def test_original_artwork_is_downscaled_for_the_player():
    """«original» у SoundCloud — больше мегабайта; раньше регекс его не ловил,
    и в Mini App грузилась исходная картинка."""
    from app.services.soundcloud import upscale_soundcloud_artwork

    url = "https://i1.sndcdn.com/artworks-abc-original.jpg"
    assert upscale_soundcloud_artwork(url).endswith("-t500x500.jpg")


def test_telegram_thumbnail_is_small_variant():
    """Bot API берёт миниатюру до 320 px; крупную вшитую обложку плеер игнорирует
    и трек выглядит без картинки — ровно то, что увидел владелец."""
    from app.services.soundcloud import thumbnail_soundcloud_artwork

    assert thumbnail_soundcloud_artwork(
        "https://i1.sndcdn.com/artworks-abc-original.jpg"
    ).endswith("-t200x200.jpg")


def test_no_telegram_thumbnail_for_foreign_hosts():
    """У YouTube нет такой схемы размеров — молча уходим без миниатюры."""
    from app.services.soundcloud import thumbnail_soundcloud_artwork

    assert thumbnail_soundcloud_artwork("https://img.youtube.com/vi/x/hq.jpg") == ""


def test_without_proxies_there_is_a_single_direct_attempt(monkeypatch):
    from app.config import settings
    from app.services.soundcloud import attempt_plan

    monkeypatch.setattr(settings, "proxy_list", "")
    assert attempt_plan() == [False]

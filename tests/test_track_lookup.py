from app.services.track_lookup import find_track, providers
from app.services.track_lookup.ranking import (
    Candidate,
    best_match,
    match_score,
    normalize_query,
    rank_candidates,
    to_latin,
)


def _candidate(title: str, artist: str | None = None, source: str = "soundcloud") -> Candidate:
    return Candidate(source=source, url=f"https://example/{title}", title=title, duration=180, artist=artist)


def test_translit_makes_cyrillic_and_latin_comparable():
    assert to_latin("Элджей") == "eldzhey"
    assert to_latin("Розовое вино") == "rozovoe vino"
    assert to_latin("kizaru") == "kizaru"


def test_normalize_query_drops_noise_words():
    assert normalize_query("скачать Kizaru - Фейк Айди mp3") == "kizaru feyk aydi"


def test_cyrillic_query_matches_latin_title():
    target = _candidate("Rozovoe Vino", artist="Eldzhey")
    assert match_score("Элджей розовое вино", target) > 0.8


def test_latin_query_matches_cyrillic_title():
    target = _candidate("Фейк Айди", artist="Kizaru")
    assert match_score("kizaru feik aidi", target) > 0.6


def test_typos_still_match():
    target = _candidate("Фейк Айди", artist="Kizaru")
    assert match_score("кизару фейк аиди", target) > 0.6


def test_video_clip_is_rejected():
    clip = _candidate("Kizaru - Фейк Айди (Официальный клип)", artist="Kizaru")
    assert match_score("кизару фейк айди", clip) == 0.0


def test_unrelated_track_scores_below_threshold():
    other = _candidate("Rasputin", artist="Boney M")
    assert best_match("кизару фейк айди", [other]) is None


def test_best_match_picks_closest_of_many():
    candidates = [
        _candidate("Rasputin", artist="Boney M"),
        _candidate("Rozovoe Vino (Slowed)", artist="Eldzhey"),
        _candidate("Rozovoe Vino", artist="Eldzhey, Feduk"),
    ]
    winner = best_match("элджей розовое вино", candidates)
    assert winner is not None
    assert winner.title.startswith("Rozovoe Vino")


def test_rank_candidates_drops_junk_and_sorts():
    candidates = [
        _candidate("Rasputin", artist="Boney M"),
        _candidate("Фейк Айди (клип)", artist="Kizaru"),
        _candidate("Фейк Айди", artist="Kizaru"),
    ]
    ranked = rank_candidates("кизару фейк айди", candidates)
    assert [item.title for item in ranked][0] == "Фейк Айди"
    assert all("клип" not in item.title for item in ranked)


def test_remix_and_prod_are_not_junk():
    remix = _candidate("Розовое вино (Remix)", artist="Элджей")
    assert match_score("элджей розовое вино ремикс", remix) > 0.5


def test_broken_source_does_not_break_the_search(monkeypatch):
    def failing(query, limit):
        raise RuntimeError("источник забанил")

    def working(query, limit):
        return [_candidate("Фейк Айди", artist="Kizaru", source="youtube")]

    monkeypatch.setattr(providers, "PROVIDERS", (failing, working))

    found = providers.collect_candidates("кизару фейк айди")
    assert [item.source for item in found] == ["youtube"]


def test_find_track_returns_best_across_sources(monkeypatch):
    import app.services.track_lookup as track_lookup

    # SoundCloud (быстрый путь) вернул нерелевантное → добираем YouTube и находим там
    monkeypatch.setattr(track_lookup, "search_soundcloud", lambda q, limit: [_candidate("Rasputin", artist="Boney M")])
    monkeypatch.setattr(track_lookup, "search_youtube", lambda q, limit: [_candidate("Фейк Айди", artist="Kizaru", source="youtube")])

    found = find_track("кизару фейк айди")
    assert found is not None
    assert found.title == "Фейк Айди"


def test_find_track_soundcloud_fast_path_skips_youtube(monkeypatch):
    import app.services.track_lookup as track_lookup

    # Уверенное совпадение в SoundCloud → YouTube не дёргаем (скорость)
    monkeypatch.setattr(track_lookup, "search_soundcloud", lambda q, limit: [_candidate("Фейк Айди", artist="Kizaru")])

    def youtube_must_not_run(q, limit):
        raise AssertionError("YouTube не должен вызываться при уверенном совпадении SoundCloud")

    monkeypatch.setattr(track_lookup, "search_youtube", youtube_must_not_run)
    found = find_track("кизару фейк айди")
    assert found is not None and found.source == "soundcloud"


def test_find_track_returns_none_when_nothing_matches(monkeypatch):
    import app.services.track_lookup as track_lookup

    monkeypatch.setattr(track_lookup, "search_soundcloud", lambda q, limit: [])
    monkeypatch.setattr(track_lookup, "search_youtube", lambda q, limit: [])
    assert find_track("кизару фейк айди") is None


def test_find_track_weak_query_still_returns_something(monkeypatch):
    import app.services.track_lookup as track_lookup

    # Владелец: даже по одному слову/букве выдавать трек. Уверенного совпадения нет,
    # но источник что-то вернул → отдаём топ-кандидата, а не «не нашли».
    monkeypatch.setattr(track_lookup, "search_soundcloud", lambda q, limit: [])
    monkeypatch.setattr(track_lookup, "search_youtube", lambda q, limit: [_candidate("Some Popular Song", artist="Some Artist", source="youtube")])
    found = find_track("s")
    assert found is not None
    assert found.title == "Some Popular Song"


def test_fallback_tries_both_sources_alternately(monkeypatch):
    """Замены перебираются вперемежку по источникам.

    Раньше попытки съедал один источник: список склеивался «сначала весь YouTube,
    потом весь SoundCloud», а срез обрезал его по первым четырём. Для западного
    трека это значило «YouTube ответил антиботом → трек под защитой», хотя рядом
    на SoundCloud лежала качающаяся копия.
    """
    from app.services.track_lookup import importer

    yt = [_candidate(f"yt{i}", artist="Artist", source="youtube") for i in range(4)]
    sc = [_candidate(f"sc{i}", artist="Artist", source="soundcloud") for i in range(4)]
    monkeypatch.setattr(importer, "search_youtube", lambda query, limit=5: yt)
    monkeypatch.setattr(importer, "search_soundcloud", lambda query, limit=5: sc)

    tried: list[str] = []

    def fake_download(candidate):
        tried.append(candidate.source)
        return None  # ничего не качается — интересен сам порядок перебора

    monkeypatch.setattr(importer, "download_candidate", fake_download)
    assert importer.download_with_fallback(_candidate("Original", artist="Artist")) is None
    # первая попытка — сам кандидат, дальше замены через один источник
    assert tried[1:5] == ["youtube", "soundcloud", "youtube", "soundcloud"]


def test_fallback_returns_first_downloadable_alternative(monkeypatch):
    from app.services.track_lookup import importer

    good = _candidate("sc-good", artist="Artist", source="soundcloud")
    monkeypatch.setattr(
        importer, "search_youtube",
        lambda query, limit=5: [_candidate("yt-drm", artist="Artist", source="youtube")],
    )
    monkeypatch.setattr(importer, "search_soundcloud", lambda query, limit=5: [good])
    monkeypatch.setattr(
        importer, "download_candidate",
        lambda candidate: "audio" if candidate.url == good.url else None,
    )
    assert importer.download_with_fallback(_candidate("Original", artist="Artist")) == "audio"

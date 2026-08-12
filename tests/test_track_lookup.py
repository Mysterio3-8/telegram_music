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


def test_soundcloud_artist_comes_from_title_not_account():
    """Исполнитель — из заголовка, а не из имени аккаунта.

    Заливать чужое на SoundCloud может кто угодно, и в выдаче по «Кизару»
    исполнителями значились «yarik», «Kogo», «original pidors».
    """
    from app.services.track_lookup.providers import soundcloud_candidate_fields

    assert soundcloud_candidate_fields("Кизару - Зеркало", "yarik") == ("Кизару", "Зеркало")
    # Заголовок без разделителя — тогда аккаунт единственный источник имени
    assert soundcloud_candidate_fields("Секс", "Lida") == ("Lida", "Секс")


def test_same_track_from_different_uploaders_collapses():
    """Четыре «Кизару — Зеркало» от разных заливщиков — одна строка выдачи."""
    from app.services.track_lookup.merge import dedup_candidates

    copies = [
        Candidate(source="soundcloud", url=f"https://sc/{name}", title="Зеркало",
                  duration=152, artist="Кизару", uploader=name)
        for name in ("yarik", "Kogo", "Na1tis", "original pidors")
    ]
    other = Candidate(source="soundcloud", url="https://sc/x", title="Тяжелый метал",
                      duration=293, artist="Кизару")
    result = dedup_candidates([*copies, other])
    assert [item.title for item in result] == ["Зеркало", "Тяжелый метал"]
    assert result[0].uploader == "yarik"  # остаётся первый, он же лучший по рангу


def test_popular_upload_wins_over_reupload_with_same_name():
    """При равной похожести выигрывает трек с бо́льшим числом прослушиваний.

    По запросу «Тейп» в выдаче стояли «grby - piv0liz-Тейп едет на речку» и
    «kugakrewceo», а официальные загрузки Big Baby Tape уходили вниз: текстовая
    похожесть у них была примерно одинаковой, а других доводов у нас не было.
    """
    official = Candidate(source="soundcloud", url="https://sc/official", title="Surname",
                         duration=182, artist="Big Baby Tape", popularity=5_000_000)
    reupload = Candidate(source="soundcloud", url="https://sc/reup", title="Surname",
                         duration=182, artist="Big Baby Tape", popularity=120)
    ranked = rank_candidates("big baby tape surname", [reupload, official])
    assert ranked[0].url == "https://sc/official"


def test_artist_query_puts_artist_tracks_above_songs_about_him():
    """По имени артиста сверху его треки, а не чужие песни с этим словом.

    Скрин владельца по запросу «Буда»: первым шёл «SCALLY MILANO — Буда слился»,
    а треки самого OG Buda — ниже. Слово «буда» есть у обоих, но человек искал
    артиста.
    """
    about = Candidate(source="soundcloud", url="https://sc/about", title="Буда слился",
                      duration=80, artist="SCALLY MILANO", popularity=90_000)
    artist = Candidate(source="soundcloud", url="https://sc/ogbuda", title="Плаки",
                       duration=96, artist="OG Buda", popularity=900_000)
    ranked = rank_candidates("Буда", [about, artist])
    assert ranked[0].url == "https://sc/ogbuda"


def test_mashup_loses_to_official_track():
    """«кизару я ебал твою маму» не должен стоять выше официального трека."""
    junk = Candidate(source="soundcloud", url="https://sc/junk",
                     title="кизару я ебал твою маму", duration=140,
                     artist="Ww8wW?", popularity=300)
    official = Candidate(source="soundcloud", url="https://sc/mirror", title="Зеркало",
                         duration=152, artist="Кизару", popularity=2_000_000)
    ranked = rank_candidates("Кизару", [junk, official])
    assert ranked[0].url == "https://sc/mirror"


def test_official_upload_always_above_reupload():
    """Официальный релиз выше перезалива, даже если у перезалива название ближе.

    Приоритет владельца: сперва официальные источники, всё остальное — следом.
    Поэтому официальность это старший ключ сортировки, а не ещё одно слагаемое.
    """
    reupload = Candidate(source="soundcloud", url="https://sc/reup",
                         title="Тейп", duration=150, artist="Андрей Квитка",
                         popularity=50_000, official=False)
    official = Candidate(source="soundcloud", url="https://sc/bbt",
                         title="Surname", duration=182, artist="Big Baby Tape",
                         popularity=800_000, official=True)
    ranked = rank_candidates("Тейп", [reupload, official])
    assert ranked[0].url == "https://sc/bbt"


def test_reupload_with_plain_title_is_not_official():
    """Заголовок без разделителя не делает аккаунт официальным.

    «Андрей Квитка» залил «БИГ БЕЙБИ ТЕЙП НА МАКСИМАЛКАХ» — разделителя нет,
    поэтому исполнителем становится сам аккаунт, и проверка «аккаунт совпал с
    исполнителем» срабатывала сама на себя. Перезалив уехал в официальные и
    занял первое место по запросу «Тейп».
    """
    from app.services.soundcloud_api import _to_candidate

    reupload = _to_candidate({
        "permalink_url": "https://sc/kvitka",
        "title": "БИГ БЕЙБИ ТЕЙП НА МАКСИМАЛКАХ",
        "duration": 148_000,
        "user": {"username": "Андрей Квитка"},
    })
    assert reupload is not None and reupload.official is False

    labeled = _to_candidate({
        "permalink_url": "https://sc/bbt",
        "title": "Surname",
        "duration": 182_000,
        "user": {"username": "Big Baby Tape"},
        "publisher_metadata": {"artist": "Big Baby Tape", "isrc": "RU1234500001"},
    })
    assert labeled is not None and labeled.official is True


def test_type_beats_fall_below_real_tracks():
    """Биты и фристайлы уходят под настоящие треки.

    Скрин владельца по «Драгонборн»: верный трек стоял первым, а дальше шли
    «LIL PUMP x PHARAON x BIG BABY TAPE TYPE BEAT», «[FREE] ... x LIL KRYSTALLL»
    и «FFM Freestyle». Формально это музыка, поэтому в мусор их не выкидываем —
    просто ставим после треков.
    """
    beat = Candidate(source="soundcloud", url="https://sc/beat",
                     title="LIL PUMP x BIG BABY TAPE TYPE BEAT - Драгонборн",
                     duration=201, artist="LOLANE BEATS", popularity=40_000)
    track = Candidate(source="soundcloud", url="https://sc/track", title="Dragonborn",
                      duration=176, artist="Big Baby Tape", popularity=700_000)
    ranked = rank_candidates("Драгонборн", [track, beat])
    assert ranked[0].url == "https://sc/track"
    assert ranked[-1].url == "https://sc/beat"


def test_beat_query_keeps_beats():
    """А если бит и просили — штрафа нет."""
    from app.services.track_lookup.ranking import match_score

    beat = Candidate(source="soundcloud", url="https://sc/beat", title="Драгонборн type beat",
                     duration=201, artist="LOLANE BEATS")
    assert match_score("драгонборн type beat", beat) > 0.5


def test_cyrillic_spelling_matches_english_name():
    """«Тейп» и «Tape» — одно слово, записанное на слух и по-английски.

    Транслит переводит побуквенно («тейп» → «teyp»), поэтому по запросу «Тейп»
    ни один Big Baby Tape не считался совпадением: выдача заполнялась случайными
    треками вроде «фанат кот10 — Martine Rose».
    """
    tape = _candidate("Surname", artist="Big Baby Tape")
    noise = _candidate("Martine Rose", artist="фанат кот10")
    assert match_score("Тейп", tape) > 0.5
    assert match_score("Тейп", noise) < 0.2

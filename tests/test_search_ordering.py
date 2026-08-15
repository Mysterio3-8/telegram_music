"""Порядок выдачи и битая кодировка — замер 14.08 на живых запросах.

🔴 Корневая находка: `search_candidates` возвращал список ровно в том порядке, в
каком его отдал SoundCloud, а весь модуль ranking работал ТОЛЬКО на пути «найди
один лучший трек». То есть все починки ранжирования человек в боте не видел.
"""
from app.services.mojibake import looks_broken, repair
from app.services.track_lookup import _ordered
from app.services.track_lookup.ranking import Candidate, rank_candidates


def _c(title, artist=None, official=False, popularity=0, duration=180, source="soundcloud",
       uploader=None):
    return Candidate(
        source=source, url=f"https://x/{title}", title=title, duration=duration,
        artist=artist, official=official, popularity=popularity, uploader=uploader,
    )


# --- имя исполнителя в запросе ------------------------------------------------


def test_wrong_artist_loses_despite_perfect_title_match():
    """Живой случай: по «макан назови её» первым стоял «Вадим Мулерман — Ты
    назови её Мариной». Текстово он подходит отлично, а то, что исполнитель
    совсем чужой, не учитывалось никак: artist_hit требует, чтобы ВЕСЬ запрос
    был подстрокой имени артиста, и на запросах «артист + название» он молчит."""
    from app.services.track_lookup.ranking import artist_affinity

    stranger = _c("Марина (Ты назови её Мариной)", artist="Вадим Мулерман", official=True)
    wanted = _c("Назови её", artist="MACAN", popularity=500_000)

    assert artist_affinity("макан назови её", stranger) == 0.0
    assert artist_affinity("макан назови её", wanted) == 1.0
    assert rank_candidates("макан назови её", [stranger, wanted])[0] is wanted


def test_long_artist_name_not_punished():
    """Регресс, который я сам внёс первой версией: по «тейп» никому не
    известный артист с именем ровно «Teyp» обходил Big Baby Tape, потому что у
    того совпадало одно слово из трёх. Спор одинаково подходящих артистов должен
    решаться прослушиваниями, а не длиной имени."""
    from app.services.track_lookup.ranking import artist_affinity

    bbt = _c("Gimme The Loot", artist="Big Baby Tape", popularity=3_000_000)
    obscure = _c("Circles", artist="Teyp", popularity=300)

    assert artist_affinity("тейп", bbt) == 1.0
    assert artist_affinity("тейп", obscure) == 1.0
    assert rank_candidates("тейп", [obscure, bbt])[0] is bbt


def test_partial_artist_match_counts_partially():
    from app.services.track_lookup.ranking import artist_affinity

    band = _c("Дышать", artist="Три дня дождя")
    assert artist_affinity("три дня дождя дышать", band) == 1.0
    # Запрос целиком укладывается в имя артиста — это тоже полное попадание
    assert artist_affinity("три дождя", band) == 1.0
    # А вот чужой артист не должен получать ничего
    assert artist_affinity("три дня дождя дышать", _c("Дышать", artist="Zivert")) == 0.0


def test_unparsed_artist_falls_back_to_title_and_channel():
    """У кандидатов YouTube исполнитель часто не разобран. Ведущее слово запроса
    в названии или канале — это догадка, поэтому вес половинный."""
    from app.services.track_lookup.ranking import artist_affinity

    yt = _c("Macan - Плачь, но не звони", uploader="GOLDEN SOUND")
    assert artist_affinity("макан плачь", yt) == 0.5
    assert artist_affinity("зиверт", yt) == 0.0


# --- название решает отдельно от общего счёта ---------------------------------


def test_official_wrong_song_loses_to_right_song():
    """Живой случай: по «три дня дождя дышать» первым шёл «Три дня дождя — Вдох»
    (0.78, официальный, 1.28 млн), а «Всю ночь тобой дышать» (0.92) стоял
    ТРИНАДЦАТЫМ. Три слова из четырёх совпадали у обоих — это имя группы, — и
    решающее слово «дышать» тонуло в общем счёте."""
    from app.services.track_lookup.ranking import title_hit

    wrong = _c("Вдох", artist="Три дня дождя", official=True, popularity=1_282_293)
    right = _c("Всю ночь тобой дышать", artist="Три дня дождя", popularity=156_220)

    assert title_hit("три дня дождя дышать", wrong) == 0.0
    assert title_hit("три дня дождя дышать", right) == 1.0
    assert rank_candidates("три дня дождя дышать", [wrong, right])[0] is right


def test_bare_artist_query_not_punished():
    """В запросе «кизару» названия нет вовсе — спрашивать с кандидата нечего."""
    from app.services.track_lookup.ranking import title_hit

    assert title_hit("кизару", _c("Яд", artist="KIZARU")) == 1.0
    assert title_hit("", _c("Яд", artist="KIZARU")) == 1.0


def test_official_still_wins_when_titles_match_equally():
    """Официальность не обесценена: при одинаковом попадании в название она
    по-прежнему решает."""
    official = _c("Вечеринка", artist="Скриптонит", official=True, popularity=1000)
    reupload = _c("Вечеринка", artist="Скриптонит", popularity=1000)

    assert rank_candidates("скриптонит вечеринка", [reupload, official])[0] is official


# --- неизвестная популярность не приговор -------------------------------------


def test_unknown_popularity_does_not_punish_youtube():
    """YouTube прослушивания не отдаёт вовсе: ноль там значит «неизвестно», а не
    «никто не слушал». Считая его настоящим нулём, мы отнимали у каждого
    кандидата YouTube треть веса — выше 0.6 он не поднимался в принципе."""
    exact_yt = _c("Fake ID", artist="Kizaru", source="youtube", popularity=0)
    parody_sc = _c("кизяка фейк айди", artist="neejvz", official=True, popularity=41)

    assert rank_candidates("кизару фейк айди", [parody_sc, exact_yt])[0] is exact_yt


# --- официальность больше не неоспорима ------------------------------------------


def test_parody_with_41_plays_loses_to_real_release():
    """Живой случай: по «кизару фейк айди» первой стояла пародия «neejvz —
    кизяка фейк айди» с 41 прослушиванием, потому что заливщик заполнил
    publisher_metadata и получил official=True. Признак ставит сам загрузчик —
    делать его старшим ключом нельзя."""
    parody = _c("кизяка фейк айди", artist="neejvz", official=True, popularity=41)
    real = _c("Fake ID", artist="Kizaru", official=False, popularity=2_000_000)

    ranked = rank_candidates("кизару фейк айди", [parody, real])
    assert ranked[0] is real


def test_official_still_beats_reupload_of_similar_quality():
    """Прибавка за официальность осталась: при прочих равных релиз
    правообладателя обязан быть выше чужого перезалива."""
    official = _c("Yamakasi", artist="Miyagi & Andy Panda", official=True, popularity=100_000)
    reupload = _c("Yamakasi", artist="Miyagi & Andy Panda", official=False, popularity=100_000)

    ranked = rank_candidates("miyagi yamakasi", [official, reupload])
    assert ranked[0] is official


def test_popular_exact_match_beats_obscure_reupload():
    """«Miyagi & Andy Panda — Yamakasi» с 16.7 млн прослушиваний стоял ШЕСТЫМ,
    а первым — чужой реаплоад с 1.9 млн и худшим совпадением."""
    hit = _c("Yamakasi", artist="Miyagi & Andy Panda", official=True, popularity=16_700_000)
    noise = _c("Мияги Там ревели горы (1950s SOUL)", artist="Busuioc", official=True, popularity=1_756)

    ranked = rank_candidates("мияги ямакаси", [hit, noise])
    assert ranked[0] is hit


# --- ранжирование доезжает до списка в боте ----------------------------------------


def test_ordered_actually_sorts():
    weak = _c("Случайный трек", artist="Кто-то", popularity=10)
    strong = _c("Панелька", artist="Хаски", official=True, popularity=500_000)

    assert _ordered("хаски панелька", [weak, strong])[0] is strong


def test_ordered_keeps_everything_when_ranking_drops_all():
    """Приоритет владельца — охват: лучше показать сомнительное, чем пустой
    экран. Ранжирование отбрасывает нулевые совпадения, и если отбросило всё,
    отдаём исходный список."""
    too_long = _c("Сборник на три часа", duration=99_999)
    assert rank_candidates("что угодно", [too_long]) == []
    assert _ordered("что угодно", [too_long]) == [too_long]


# --- битая кодировка ----------------------------------------------------------------


def test_broken_cyrillic_is_repaired():
    assert repair("Ðÿäîì áûòü") == "Рядом быть"


def test_normal_text_untouched():
    for text in ("Мияги И Эндшпиль", "Big Baby Tape", "HUMBLE.", ""):
        assert repair(text) == text


def test_western_text_not_mangled():
    """Björk и Café — настоящий западноевропейский текст, а не битая кириллица.
    Испортить его починкой было бы хуже, чем не чинить вовсе."""
    for text in ("Björk", "Café del Mar", "Motörhead", "Sigur Rós"):
        assert repair(text) == text


def test_looks_broken_detects_only_suspicious():
    assert looks_broken("Ðÿäîì áûòü")
    assert not looks_broken("Рядом быть")
    assert not looks_broken("Plain ASCII title")
    assert not looks_broken("")

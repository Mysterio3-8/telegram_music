"""Порядок выдачи и битая кодировка — замер 14.08 на живых запросах.

🔴 Корневая находка: `search_candidates` возвращал список ровно в том порядке, в
каком его отдал SoundCloud, а весь модуль ranking работал ТОЛЬКО на пути «найди
один лучший трек». То есть все починки ранжирования человек в боте не видел.
"""
from app.services.mojibake import looks_broken, repair
from app.services.track_lookup import _ordered
from app.services.track_lookup.ranking import Candidate, rank_candidates


def _c(title, artist=None, official=False, popularity=0, duration=180, source="soundcloud"):
    return Candidate(
        source=source, url=f"https://x/{title}", title=title, duration=duration,
        artist=artist, official=official, popularity=popularity,
    )


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

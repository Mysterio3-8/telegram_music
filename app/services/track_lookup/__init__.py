"""Поиск трека по свободному запросу пользователя сразу во всех источниках.

Массовое пополнение каталога 24/7 работает только с SoundCloud; этот модуль —
вторая, независимая ветка: пользователь пишет запрос как угодно, а мы ищем везде
и выбираем лучшее совпадение. Вызовы блокирующие (yt-dlp) — оборачивать
в asyncio.to_thread на стороне вызывающего.
"""
import asyncio
import logging

from app.config import settings
from app.services.track_lookup.merge import dedup_candidates, dedup_key, merge_candidates
from app.services.track_lookup.providers import (
    PROVIDERS,
    SOURCE_SOUNDCLOUD,
    SOURCE_YOUTUBE,
    collect_candidates,
    looks_like_music,
    search_soundcloud,
    search_youtube,
)
from app.services.title_quality import is_probably_junk
from app.services.track_lookup.ranking import (
    Candidate,
    best_match,
    is_track_duration,
    match_score,
    normalize_query,
    rank_candidates,
    to_latin,
)

# Порог уверенного совпадения понижен: владелец хочет выдачу даже по слабому
# запросу. best_match вызываем с ним; ниже порога — фолбэк на топ (см. find_track).
logger = logging.getLogger(__name__)

CONFIDENT_MATCH = 0.3


def _safe_search(provider, query: str, limit: int) -> list[Candidate]:
    try:
        return provider(query, limit)
    except Exception:  # noqa: BLE001 — источник отвалился, не роняем поиск
        # Логируем громко: молчаливый отказ SoundCloud незаметно оставляет выдачу
        # на одном YouTube, и «поиск стал хуже» превращается в загадку.
        logger.warning("Живой поиск: источник %s не ответил", provider.__name__, exc_info=True)
        return []


def find_track(query: str, limit: int = 4) -> Candidate | None:
    """Лучшее совпадение по запросу среди источников; None — не нашли.

    Быстрый путь (скорость — приоритет владельца): сперва только SoundCloud —
    там готовый mp3 без перекодирования. Если совпадение уверенное, YouTube даже
    не дёргаем (одна сетевая операция вместо двух). Иначе добираем YouTube и
    ранжируем всё вместе.

    Выдаём трек даже по слабому запросу (одно слово/буква/только артист): ниже
    порога — топ по ранжированию. None только если источники не вернули ничего."""
    sc = _safe_search(search_soundcloud, query, limit)
    confident = best_match(query, sc, min_score=CONFIDENT_MATCH)
    if confident is not None:
        return confident

    candidates = sc + _safe_search(search_youtube, query, limit)
    confident = best_match(query, candidates, min_score=CONFIDENT_MATCH)
    if confident is not None:
        return confident
    ranked = rank_candidates(query, candidates)
    if ranked:
        return ranked[0]
    # Последний шанс — топ выдачи, но НЕ мусор: клип и часовой микс лучше
    # не отдавать вовсе, чем отдать вместо трека (приоритет владельца).
    for candidate in candidates:
        if not is_probably_junk(candidate.title) and is_track_duration(candidate.duration):
            return candidate
    return None


def _visible_candidates(query: str, candidates: list[Candidate]) -> list[Candidate]:
    """Кандидаты в порядке для показа: сперва совпавшие по названию и артисту,
    следом всё остальное, что вернул источник.

    Ранжирование меняет ПОРЯДОК, но больше ничего не выбрасывает. Причина — фиты:
    «Big Baby Tape — DUO» это трек с Кизару, но в названии и в поле артиста его
    имени нет, оно живёт в описании и тегах SoundCloud. Наш счёт давал такому
    треку ноль, и он исчезал из выдачи, хотя источник вернул его по этому самому
    запросу — то есть совпадение у себя нашёл. Доверяем источнику: он искал по
    полям, которых у нас на руках нет.

    Отсеиваем только явную не-музыку и то, что вне границ длительности.
    """
    from app.services.track_lookup.ranking import popularity_weight

    ranked = rank_candidates(query, candidates)
    seen = {id(item) for item in ranked}
    rest = [
        item
        for item in candidates
        if id(item) not in seen
        and not is_probably_junk(item.title)
        and is_track_duration(item.duration)
    ]
    # Хвост — это кандидаты, которых источник вернул по запросу, а наше
    # сопоставление текста в них ничего не узнало (фиты, а ещё запросы вроде
    # «Тейп», где кириллица и латиница пишутся по-разному). Раньше они шли в
    # сыром порядке SoundCloud, и «фанат кот10 — Martine Rose» оказывался выше
    # «Big Baby Tape — NOBODY». Порядок внутри хвоста: официальные, потом по
    # прослушиваниям.
    rest.sort(key=lambda item: (0 if item.official else 1, -popularity_weight(item.popularity)))
    return ranked + rest


def is_russian_repertoire(query: str) -> bool:
    """Кириллица в запросе — значит ищут русский репертуар.

    Идея владельца, и она попадает в реальную картину: русское почти всё лежит
    на SoundCloud, а западные мейджоры там под DRM (yt-dlp: «This video is DRM
    protected») — качаются они с YouTube, из официальных каналов «- Topic».
    Поэтому кириллический запрос обслуживает SoundCloud, а латинский обязан
    спросить и YouTube, а не ждать, пока SoundCloud наберёт мало совпадений.
    """
    return any("а" <= char.lower() <= "я" or char.lower() == "ё" for char in query)


async def search_candidates(query: str, limit: int | None = None) -> list[Candidate]:
    """Список найденных треков по свободному запросу — из источников, не из базы.

    SoundCloud — музыкальный каталог, поэтому он основной и идёт целиком. YouTube
    подключается, только если SoundCloud набрал мало: он видеохостинг, и на запрос
    «секс» честно отдаёт ролики про игрушки и про биологию. Из его выдачи берём
    лишь то, что по форме похоже на трек (см. looks_like_music), и только то, чего
    в SoundCloud не нашлось.
    """
    per_source = limit or settings.live_search_limit
    russian = is_russian_repertoire(query)
    if russian:
        soundcloud = await _search_soundcloud_variants(query, per_source)
        if _confident_count(query, soundcloud) >= settings.youtube_fallback_min_results:
            return _ordered(query, soundcloud)
        youtube = await asyncio.to_thread(_safe_search, search_youtube, query, per_source)
    else:
        # Латиница — западный репертуар: оба источника сразу и параллельно, время
        # ответа равно медленному из двух, а не их сумме. Ждать, пока SoundCloud
        # «наберёт мало», тут нельзя: он набирает много, только всё под DRM.
        soundcloud, youtube = await asyncio.gather(
            _search_soundcloud_variants(query, per_source),
            asyncio.to_thread(_safe_search, search_youtube, query, per_source),
        )
    music = [item for item in _visible_candidates(query, youtube) if looks_like_music(item)]
    return _ordered(query, merge_candidates(soundcloud, music))


def _ordered(query: str, candidates: list[Candidate]) -> list[Candidate]:
    """Порядок выдачи для человека.

    🔴 До 14.08 здесь не было ничего: список уходил в бот ровно таким, каким его
    отдал SoundCloud, а весь модуль ranking (фонетика, популярность,
    официальность, штрафы за slowed/reverb и биты) работал ТОЛЬКО на пути
    «найди один лучший трек». То есть починки ранжирования, сделанные 12–13.08,
    человек в списке не видел вовсе.

    Как это выглядело на замере: по «мияги там ямакаси» первым стоял чужой
    реаплоад с битой кодировкой в названии, а «Miyagi & Andy Panda — Yamakasi» с
    16.7 млн прослушиваний — шестым.

    Пустой результат ранжирования отдаём как есть, неотсортированным: приоритет
    владельца — охват. Лучше показать сомнительное, чем пустой экран (то же
    решение, что и в `find_track`).
    """
    ranked = rank_candidates(query, candidates)
    return ranked or candidates


async def _search_soundcloud_variants(query: str, limit: int) -> list[Candidate]:
    """SoundCloud + тот же запрос в латинице, если исходный кириллицей.

    Поиск SoundCloud буквальный: «Фейк ид» он с «Fake ID» не сопоставляет.
    Транслитерация у нас раньше работала только на ранжировании — то есть
    чинила порядок уже найденного, а не само нахождение. Оба варианта уходят
    параллельно, результаты склеиваются с дедупом.
    """
    variants = [query]
    latin = to_latin(query)
    if latin != query.lower():
        variants.append(latin)
    results = await asyncio.gather(
        *(
            asyncio.to_thread(_safe_search, search_soundcloud, variant, limit)
            for variant in variants
        )
    )
    merged: list[Candidate] = []
    for found in results:
        merged = merge_candidates(merged, _visible_candidates(query, found))
    # Один трек, залитый десятком аккаунтов, — это десять строк выдачи об одном и
    # том же. Схлопываем: артист теперь разбирается из заголовка, поэтому копии
    # наконец имеют одинаковый ключ.
    return dedup_candidates(merged)


def _confident_count(query: str, candidates: list[Candidate]) -> int:
    """Сколько кандидатов реально похожи на запрос.

    Считаем именно совпадения, а не строки в ответе: на «Фейк ид» SoundCloud
    возвращал полтора десятка чужих треков, порог «набралось много» срабатывал,
    и YouTube — который такие запросы разбирает заметно лучше — не спрашивался
    вовсе. Нужного трека человек не видел при формально полной выдаче.
    """
    return sum(1 for item in candidates if match_score(query, item) >= CONFIDENT_MATCH)


__all__ = [
    "Candidate",
    "PROVIDERS",
    "SOURCE_SOUNDCLOUD",
    "SOURCE_YOUTUBE",
    "best_match",
    "collect_candidates",
    "dedup_key",
    "find_track",
    "merge_candidates",
    "search_candidates",
    "is_track_duration",
    "match_score",
    "normalize_query",
    "rank_candidates",
    "search_soundcloud",
    "search_youtube",
    "to_latin",
]

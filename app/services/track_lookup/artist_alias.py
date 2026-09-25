"""Кириллическое имя артиста → его латинское написание из нашей базы артистов.

Живой прогон 25.09: по «биг бейби тейп драгонборн» бот не находил Big Baby Tape
вовсе — только самоделки с «Биг Бейби Тейп» в названии («Бит Тайп…», «4x4
[Tophaip.com]»). SoundCloud ищет буквально, а наш побуквенный транслит даёт
«big beybi teyp», которого там нет. Зато в таблице `artists` одиннадцать тысяч
латинских имён, и на слух «биг бейби тейп» с «Big Baby Tape» совпадает
(`phonetic`). Отсюда лишний вариант запроса «Big Baby Tape dragonborn» — ещё
один параллельный запрос к SoundCloud, около 0.3 сек, и только для кириллицы.

Читается напрямую через sqlite3 в потоке, а не через сессию SQLAlchemy: поиск
зовут и бот, и API, и воркеры со своим циклом событий на каждую задачу, а
асинхронный движок к циклу привязан. На PostgreSQL модуль молча выключается —
поиск работает как раньше, просто без этой подсказки.
"""
from __future__ import annotations

import json
import logging
import re
import sqlite3
import threading
import time
from difflib import SequenceMatcher

from app.services.track_lookup.ranking import normalize_query, phonetic

logger = logging.getLogger(__name__)

_CACHE_TTL = 6 * 3600
_MAX_PREFIX_WORDS = 4
# «big babi tap» против «big baby tap» — 0.92. Ниже 0.88 начинаются чужие имена.
_MIN_RATIO = 0.88
# Одно слово — самое опасное место: «вечно» на слух похоже на чьё-нибудь имя.
# Короткие одиночные имена не подставляем вовсе, длинные — только почти точно.
_SINGLE_WORD_MIN_LEN = 5
_SINGLE_WORD_RATIO = 0.93
_CYRILLIC = re.compile("[а-яё]", re.I)
_LATIN = re.compile("[a-z]", re.I)

# phonetic → (имя, число слов); по первой букве, чтобы не сравнивать со всеми
_index: dict[str, list[tuple[str, str, int]]] = {}
_loaded_at = 0.0
_lock = threading.Lock()


def _database_path() -> str | None:
    from sqlalchemy.engine import make_url

    from app.config import settings

    url = make_url(settings.database_url)
    if not url.drivername.startswith("sqlite") or not url.database or url.database == ":memory:":
        return None
    return url.database


def _load_names() -> list[str]:
    path = _database_path()
    if path is None:
        return []
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
        try:
            rows = connection.execute("select name, aliases from artists").fetchall()
        finally:
            connection.close()
    except sqlite3.Error:
        logger.warning("Имена артистов не прочитались — подсказка латиницей выключена", exc_info=True)
        return []
    names: list[str] = []
    for name, aliases in rows:
        names.append(name or "")
        try:
            names.extend(item for item in json.loads(aliases or "[]") if isinstance(item, str))
        except (TypeError, ValueError):
            pass
    return names


def build_index(names: list[str]) -> dict[str, list[tuple[str, str, int]]]:
    """Только латинские имена: смысл модуля — найти латиницу по кириллице."""
    index: dict[str, list[tuple[str, str, int]]] = {}
    for name in names:
        name = (name or "").strip()
        if not name or not _LATIN.search(name) or _CYRILLIC.search(name):
            continue
        key = phonetic(normalize_query(name))
        if not key:
            continue
        index.setdefault(key[0], []).append((key, name, len(key.split())))
    return index


def _get_index() -> dict[str, list[tuple[str, str, int]]]:
    global _index, _loaded_at
    with _lock:
        if not _index or time.monotonic() - _loaded_at > _CACHE_TTL:
            _index = build_index(_load_names())
            _loaded_at = time.monotonic()
        return _index


def latin_variant(query: str, index: dict[str, list[tuple[str, str, int]]] | None = None) -> str | None:
    """«биг бейби тейп драгонборн» → «Big Baby Tape dragonborn». None — нечего подставить.

    Берётся самое длинное начало запроса (до четырёх слов), которое на слух
    совпало с известным артистом: люди пишут «артист название».
    """
    if not _CYRILLIC.search(query or ""):
        return None
    if index is None:
        index = _get_index()
    if not index:
        return None
    words = normalize_query(query).split()
    for size in range(min(_MAX_PREFIX_WORDS, len(words)), 0, -1):
        prefix = phonetic(" ".join(words[:size]))
        if not prefix:
            continue
        if size == 1 and len(prefix) < _SINGLE_WORD_MIN_LEN:
            continue
        need = _SINGLE_WORD_RATIO if size == 1 else _MIN_RATIO
        best_name, best_ratio = None, need
        for key, name, word_count in index.get(prefix[0], ()):
            if word_count != size or abs(len(key) - len(prefix)) > 2:
                continue
            ratio = SequenceMatcher(None, prefix, key).ratio()
            if ratio >= best_ratio:
                best_name, best_ratio = name, ratio
        if best_name:
            return " ".join([best_name, *words[size:]]).strip()
    return None

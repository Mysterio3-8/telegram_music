"""Нормализованный поисковый ключ трека (требование владельца: находить по автору,
названию, любому слову, любой букве — включая кириллицу).

Зачем отдельное поле: SQLite `lower()`/`ILIKE` понижают регистр только для ASCII,
поэтому «Кизару» и «кизару» для базы разные строки и поиск по русской букве не
работал. Ключ считаем в Python (регистр + транслит) и ищем LIKE по нему.

Транслит в обе стороны даёт бонус: «kizaru» находит «Кизару», «кизару» — «Kizaru».
"""
from app.services.track_lookup.ranking import to_latin


def build_search_index(artist: str | None, title: str | None) -> str:
    """«исполнитель название» в нижнем регистре, оригинал + латиница.

    Оба варианта в одной строке: подстрочный поиск найдёт и кириллическое
    написание, и транслит, без второго запроса к базе."""
    parts = [(artist or "").strip().lower(), (title or "").strip().lower()]
    original = " ".join(part for part in parts if part)
    latin = to_latin(original)
    if latin == original:
        return original
    return f"{original} {latin}"


def normalize_search_query(query: str) -> str:
    """Запрос к тому же виду. Пустая строка — искать нечего."""
    return (query or "").strip().lower()

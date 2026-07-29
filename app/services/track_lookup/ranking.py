"""Сопоставление свободного запроса пользователя с найденными кандидатами.

Запрос приходит как угодно: кириллицей, транслитом, с опечатками, на любом языке
(«Kizaru фейк айди», «Элджей розовое вино», «eldjay rozovoe vino»). Обе стороны
приводим к латинице и сравниваем — так транслит и кириллица совпадают между собой.
Здесь только вычисления: ни сети, ни БД.
"""
from dataclasses import dataclass
from difflib import SequenceMatcher

from app.services.title_quality import is_probably_junk

_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "c", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    "і": "i", "ї": "yi", "є": "e", "ґ": "g",
}


@dataclass(frozen=True)
class Candidate:
    """Найденный в источнике трек — до скачивания, только метаданные."""

    source: str
    url: str
    title: str
    duration: int
    artist: str | None = None
    cover_url: str | None = None

    @property
    def full_title(self) -> str:
        return f"{self.artist} {self.title}" if self.artist else self.title


def to_latin(text: str) -> str:
    """Кириллица → латиница. Уже латинский текст остаётся как есть."""
    return "".join(_TRANSLIT.get(char, char) for char in text.lower())


# Слова-паразиты запроса («скачать … mp3») — в латинице, сравнение идёт после транслита
_NOISE_WORDS = frozenset(
    to_latin(word)
    for word in (
        "mp3", "flac", "музыка", "music", "song", "трек", "track",
        "слушать", "listen", "онлайн", "online", "бесплатно", "free",
        "скачать", "download", "полная", "версия", "version",
    )
)

# Опечатка в длинном слове допустима: «feik» ↔ «feyk», «аиди» ↔ «айди»
_TYPO_RATIO = 0.7
_TYPO_MIN_LENGTH = 4


def normalize_query(text: str) -> str:
    """Приводит запрос к виду, сравнимому с названием трека."""
    latin = to_latin(text)
    cleaned = "".join(char if char.isalnum() or char.isspace() else " " for char in latin)
    words = [word for word in cleaned.split() if word not in _NOISE_WORDS]
    return " ".join(words)


def _tokens_match(token: str, word: str) -> bool:
    """Слова совпадают точно, как префикс или с опечаткой в пределах допустимого."""
    if token.startswith(word) or word.startswith(token):
        return True
    if min(len(token), len(word)) < _TYPO_MIN_LENGTH:
        return False
    return SequenceMatcher(None, token, word).ratio() >= _TYPO_RATIO


def _token_coverage(query_tokens: list[str], target_tokens: set[str]) -> float:
    """Доля слов запроса, нашедшихся в названии — с учётом склонений и опечаток."""
    if not query_tokens:
        return 0.0
    hits = sum(1 for token in query_tokens if any(_tokens_match(token, w) for w in target_tokens))
    return hits / len(query_tokens)


def is_track_duration(seconds: int) -> bool:
    """«Это вообще трек?» по длительности (приоритет владельца: только музыка).
    0 — источник не сообщил длительность: пропускаем, проверим после скачивания.
    Границы — settings.search_min_seconds/search_max_seconds."""
    if not seconds:
        return True
    from app.config import settings

    if settings.search_min_seconds and seconds < settings.search_min_seconds:
        return False  # джингл, обрезок, голосовое
    if settings.search_max_seconds and seconds > settings.search_max_seconds:
        return False  # часовой микс, подкаст, «весь альбом одним файлом»
    return True


def match_score(query: str, candidate: Candidate) -> float:
    """Похожесть запроса на кандидата, 0.0—1.0. Клипы, промо и не-треки по
    длительности получают 0 — до скачивания, чтобы не тратить на них время."""
    if is_probably_junk(candidate.title):
        return 0.0
    if not is_track_duration(candidate.duration):
        return 0.0
    normalized_query = normalize_query(query)
    normalized_target = normalize_query(candidate.full_title)
    if not normalized_query or not normalized_target:
        return 0.0

    ratio = SequenceMatcher(None, normalized_query, normalized_target).ratio()
    coverage = _token_coverage(normalized_query.split(), set(normalized_target.split()))
    # Покрытие слов важнее посимвольного сходства: длинное название с лишними
    # словами («… (Official Audio)») не должно топить точное совпадение.
    return round(coverage * 0.7 + ratio * 0.3, 4)


def rank_candidates(query: str, candidates: list[Candidate]) -> list[Candidate]:
    """Кандидаты от лучшего к худшему. Мусор и нулевые совпадения отброшены."""
    scored = [(match_score(query, item), item) for item in candidates]
    return [item for score, item in sorted(scored, key=lambda row: -row[0]) if score > 0]


def best_match(query: str, candidates: list[Candidate], min_score: float = 0.45) -> Candidate | None:
    """Лучший кандидат или None, если ничего не дотянуло до порога."""
    for candidate in rank_candidates(query, candidates):
        if match_score(query, candidate) >= min_score:
            return candidate
    return None

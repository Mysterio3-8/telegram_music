"""Сопоставление свободного запроса пользователя с найденными кандидатами.

Запрос приходит как угодно: кириллицей, транслитом, с опечатками, на любом языке
(«Kizaru фейк айди», «Элджей розовое вино», «eldjay rozovoe vino»). Обе стороны
приводим к латинице и сравниваем — так транслит и кириллица совпадают между собой.
Здесь только вычисления: ни сети, ни БД.
"""
import math
import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from app.services.title_quality import is_beat_or_instrumental, is_probably_junk

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
    # Канал/автор загрузки. Отдельно от artist сознательно: у YouTube это имя
    # канала, и в сопоставление его пускать нельзя (сломает дедуп с SoundCloud),
    # но фильтру «похоже ли на музыку» он нужен — «Исполнитель - Topic» это
    # автоматический музыкальный канал.
    uploader: str | None = None
    # Прослушивания у источника. Нужны как решающий довод при похожих названиях:
    # официальная загрузка артиста набирает миллионы, самопальный реаплоад —
    # сотни. Без этого в выдаче по «Тейп» первым мог стоять «grby - piv0liz-Тейп
    # едет на речку», а официальный Big Baby Tape — на третьей странице.
    # 0 — источник счётчика не дал (YouTube), тогда порядок решает похожесть.
    popularity: int = 0
    # Официальная ли это загрузка: релиз правообладателя или верифицированного
    # аккаунта артиста, а не чужой реаплоад, мэшап и «slowed + reverb».
    # Приоритет владельца: сперва официальные, всё остальное — следом.
    official: bool = False

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


# Один звук, записанный по-разному. Кириллица транслитерируется буква в букву
# («тейп» → «teyp»), а по-английски то же слово пишется «tape» — сопоставление
# промахивалось, и по запросу «Тейп» ни один Big Baby Tape не считался
# совпадением. Сводим написания к общему виду ПОСЛЕ транслита.
_PHONETIC = (
    ("ey", "a"),    # teyp → tap(e), beybi → babi
    ("ay", "i"),    # rayd → rid
    ("iy", "i"),
    ("dzh", "j"),   # dzhon → jon
    ("kh", "h"),
    ("ts", "c"),
    ("yu", "u"),
    ("ya", "a"),
    ("e", "a"),     # tap ↔ tape после отбрасывания немого «e» ниже
)


def phonetic(text: str) -> str:
    """Грубая фонетическая свёртка: одинаково звучащее пишется одинаково."""
    result = to_latin(text)
    for source, target in _PHONETIC:
        result = result.replace(source, target)
    # Удвоенные буквы и немая гласная на конце слова ничего не решают:
    # «tape» → «tapa» → «tap», и это сходится с «тейп» → «teyp» → «tap».
    result = re.sub('(.)\\1+', '\\1', result)
    return re.sub('a\\b', "", result)


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


# Пере-версии трека: их не нужно отдавать, когда человек просил оригинал.
# Слова в латинице — сравнение идёт после транслита (to_latin).
_VERSION_MARKERS = tuple(
    to_latin(word)
    for word in (
        "slowed", "reverb", "sped up", "spedup", "nightcore", "8d", "bass boosted",
        "bassboosted", "mashup", "cover", "karaoke", "instrumental", "минус",
        "ремикс", "remix", "edit", "flip", "acapella", "а капелла", "tiktok",
        "ускоренная", "замедленная",
    )
)
_VERSION_PENALTY = 0.45  # версия проигрывает оригиналу, но остаётся в выдаче


_BEAT_PENALTY = 0.35


def version_penalty(query: str, title: str) -> float:
    """1.0 — штрафа нет; <1 — название это пере-версия, а просили оригинал.

    Просят «kizaru fake id» → «(Slowed + Reverb)» отодвигается за оригинал.
    Упомянули любую версию («розовое вино slowed», «… ремикс») — штраф выключается
    целиком: человек ищет именно версию, и придираться к точному слову не нужно
    («ремикс» и «remix» — одно и то же намерение)."""
    query_latin = to_latin(query)
    if any(marker in query_latin for marker in _VERSION_MARKERS):
        return 1.0
    title_latin = to_latin(title)
    if any(marker in title_latin for marker in _VERSION_MARKERS):
        return _VERSION_PENALTY
    return 1.0


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

    def similarity(left: str, right: str) -> float:
        ratio = SequenceMatcher(None, left, right).ratio()
        coverage = _token_coverage(left.split(), set(right.split()))
        # Покрытие слов важнее посимвольного сходства: длинное название с лишними
        # словами («… (Official Audio)») не должно топить точное совпадение.
        return coverage * 0.7 + ratio * 0.3

    # Считаем дважды: буква в букву и на слух. Транслит переводит побуквенно
    # («Тейп» → «teyp»), а по-английски то же слово пишется «tape» — по запросу
    # «Тейп» ни один Big Baby Tape не считался совпадением, выдача заполнялась
    # случайными треками. Берём лучшее из двух: точное написание не проигрывает,
    # а разное написание одного звука перестаёт быть промахом.
    score = max(
        similarity(normalized_query, normalized_target),
        similarity(phonetic(normalized_query), phonetic(normalized_target)),
    )
    # Оригинал должен обгонять slowed/reverb/cover, если их не просили явно
    score *= version_penalty(query, candidate.full_title)
    # Бит/минус/фристайл, которого не просили, — вниз. Не выбрасываем: человеку,
    # который ищет именно бит, он нужен, и по запросу со словом «минус» штрафа
    # не будет вовсе.
    if is_beat_or_instrumental(candidate.full_title) and not is_beat_or_instrumental(query):
        score *= _BEAT_PENALTY
    return round(score, 4)


def popularity_weight(popularity: int) -> float:
    """Прослушивания → 0.0—1.0. По логарифму, а не линейно: разница между сотней
    и десятью тысячами прослушиваний существенна, между миллионом и двумя — уже
    нет. Миллион даёт единицу."""
    return min(1.0, math.log10(max(0, popularity) + 1) / 6)


def artist_hit(query: str, candidate: Candidate) -> bool:
    """Запрос — это имя исполнителя, а не слово из названия.

    Разница решающая. По запросу «Буда» слово «буда» есть и в «SCALLY MILANO —
    Буда слился» (там оно в названии, а исполнитель другой), и у самого OG Buda.
    Человек, набравший «Буда», ищет артиста, поэтому его треки должны идти
    первыми, а песни про буду — следом.
    """
    normalized = normalize_query(query)
    artist = normalize_query(candidate.artist or "")
    return bool(normalized) and bool(artist) and normalized in artist


def rank_candidates(query: str, candidates: list[Candidate]) -> list[Candidate]:
    """Кандидаты от лучшего к худшему. Мусор и нулевые совпадения отброшены.

    Порядок решают три довода вместе, а не один: похожесть текста, попадание в
    имя исполнителя и прослушивания. Одной похожести не хватало — по «Кизару»
    наверх лезли мэшапы и «кизару я ебал твою маму», потому что слово из запроса
    в них есть, а больше сравнивать было нечем.
    """
    scored = [(match_score(query, item), item) for item in candidates]

    def order(row: tuple[float, Candidate]) -> tuple[int, float]:
        score, candidate = row
        relevance = (
            score * 0.6
            + popularity_weight(candidate.popularity) * 0.3
            + (0.1 if artist_hit(query, candidate) else 0.0)
        )
        # Официальность — СТАРШИЙ ключ, а не слагаемое (решение владельца):
        # релиз правообладателя обязан стоять выше любого реаплоада, даже если
        # у реаплоада название ближе к запросу. Внутри каждой группы порядок
        # обычный — похожесть, прослушивания, имя артиста.
        return (0 if candidate.official else 1, -relevance)

    return [item for score, item in sorted(scored, key=order) if score > 0]


def best_match(query: str, candidates: list[Candidate], min_score: float = 0.45) -> Candidate | None:
    """Лучший кандидат или None, если ничего не дотянуло до порога."""
    for candidate in rank_candidates(query, candidates):
        if match_score(query, candidate) >= min_score:
            return candidate
    return None

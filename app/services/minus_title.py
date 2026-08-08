"""Разбор названий минусов с YouTube.

Канал минусов подписывает видео однообразно:

    МИНУС - Lida – пупы шмупы (poopu shmupi) Lyrics (Instrumental) #music
    МИНУС - Aarne, Платина - На бумере (Instrumental) #music

Если это залить как есть, поиск не найдёт: человек ищет «lida пупы шмупы», а в
базе лежит строка с префиксом, английской транскрипцией в скобках, пометкой
Instrumental и хештегом. Поэтому чистим до «Исполнитель — Название».
"""
import re

# Префикс минуса в начале названия — с него начинается каждое видео канала
_PREFIX_RE = re.compile(r"^\s*(минус|minus)\s*[-–—:]\s*", re.IGNORECASE)

# Хвосты, которые к названию трека отношения не имеют
_NOISE_RE = re.compile(
    r"\(\s*instrumental\s*\)|\[\s*instrumental\s*\]|"
    r"\binstrumental\b|\blyrics\b|\bклип\b|\bofficial\s+video\b|"
    r"\bбез\s+слов\b|\bминусовка\b",
    re.IGNORECASE,
)
_HASHTAG_RE = re.compile(r"#\S+")
# Транскрипция латиницей в скобках рядом с русским названием: «пупы шмупы (poopu shmupi)»
_TRANSLIT_HINT_RE = re.compile(r"\(\s*[a-z0-9 '`\-]+\s*\)", re.IGNORECASE)
_DASHES = "‐‑‒–—―−─-"
_SPLIT_RE = re.compile(f"\\s+[{_DASHES}]\\s+|\\s*[{_DASHES}]\\s*")


def clean_minus_title(raw: str) -> str:
    """Убирает префикс «МИНУС», пометки и хештеги. Возвращает «Артист - Название»."""
    text = _PREFIX_RE.sub("", raw or "")
    text = _HASHTAG_RE.sub(" ", text)
    text = _NOISE_RE.sub(" ", text)
    text = _TRANSLIT_HINT_RE.sub(" ", text)
    text = text.replace("()", " ").replace("[]", " ")
    return " ".join(text.split()).strip(" -–—:")


def parse_minus_title(raw: str) -> tuple[str, str]:
    """(исполнитель, название) из названия видео.

    Разделитель — тире в любом начертании: у людей их штук восемь разных.
    Если тире нет, исполнителя не выдумываем — пусть будет «Неизвестный»,
    это честнее, чем записать пол-названия в артисты.
    """
    cleaned = clean_minus_title(raw)
    if not cleaned:
        return "Неизвестный", (raw or "").strip() or "Без названия"

    parts = [part.strip() for part in _SPLIT_RE.split(cleaned, maxsplit=1)]
    if len(parts) == 2 and parts[0] and parts[1]:
        return parts[0], parts[1]
    return "Неизвестный", cleaned


def looks_like_minus(raw: str) -> bool:
    """Минус ли это по названию — для каналов, где лежит не только минусовка."""
    text = (raw or "").lower()
    return bool(_PREFIX_RE.match(text)) or "instrumental" in text or "минусовка" in text

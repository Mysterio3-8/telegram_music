"""Определение «не-музыкальных» названий (видеоклипы, премьеры, реакции).

Такие записи попадают в базу, когда вместо аудио скачивается видео. В TG Микс
они не должны попадать; в блоке C та же проверка используется для чистки каталога.

Важно: варианты трека — (Remix), prod., (Acoustic), (Slowed) — это НЕ мусор,
их не трогаем. Ловим только явные маркеры видео/промо.
"""
import re

# Маркеры ищем как отдельные «слова» (с границами), регистр игнорируем.
_JUNK_MARKERS = (
    r"клип",
    r"видеоклип",
    r"премьера",
    r"official\s+video",
    r"official\s+music\s+video",
    r"music\s+video",
    r"lyric\s+video",
    r"lyrics\s+video",
    r"лирик[-\s]?видео",
    r"трейлер",
    r"trailer",
    r"обзор",
    r"реакци[яи]",
    r"reaction",
)

_JUNK_RE = re.compile(r"(?:^|[\s\(\[\|/–—-])(?:" + "|".join(_JUNK_MARKERS) + r")(?:$|[\s\)\]\|/–—-])", re.IGNORECASE)


def is_probably_junk(title: str) -> bool:
    """True — название похоже на видео/промо, а не на музыкальный трек."""
    if not title:
        return False
    return bool(_JUNK_RE.search(title))

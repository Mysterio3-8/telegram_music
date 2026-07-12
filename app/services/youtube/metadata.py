"""Разбор названия YouTube-видео на исполнителя и название трека (доп. ТЗ, §7).

«DJ KL - Акап (Official Audio)» → artist «DJ KL», title «Акап».
Поддержаны разделители «-», «—», «–»; вырезаются технические пометки.
"""
import re

# Технические пометки (доп. ТЗ, §7). Регистронезависимо.
_TECH_TOKENS = (
    "official music video",
    "official audio",
    "official video",
    "official clip",
    "lyric video",
    "visualizer",
    "lyrics",
    "audio",
    "премьера",
    "официальное аудио",
    "официальное видео",
    "официальный клип",
)

_SEPARATOR = re.compile(r"\s[-–—]\s")
_MULTISPACE = re.compile(r"\s+")
_BRACKETS = re.compile(r"\(([^()]*)\)|\[([^\[\]]*)\]")


def _drop_tech_brackets(match: re.Match[str]) -> str:
    inner = (match.group(1) or match.group(2) or "").lower()
    return "" if any(token in inner for token in _TECH_TOKENS) else match.group(0)


def _clean(text: str) -> str:
    text = _BRACKETS.sub(_drop_tech_brackets, text)
    for token in _TECH_TOKENS:
        text = re.sub(rf"\b{re.escape(token)}\b", "", text, flags=re.IGNORECASE)
    text = _MULTISPACE.sub(" ", text)
    return text.strip(" -–—|·•")


def parse_title(video_title: str, fallback_artist: str) -> tuple[str, str]:
    """Возвращает (исполнитель, название). Без разделителя — исполнитель это fallback."""
    parts = _SEPARATOR.split(video_title.strip(), maxsplit=1)
    if len(parts) == 2:
        artist = _clean(parts[0])
        title = _clean(parts[1])
        if artist and title:
            return artist, title

    title = _clean(video_title) or video_title.strip()
    return fallback_artist.strip() or "Unknown", title

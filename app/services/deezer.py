"""Публичный Deezer API (без ключей): фото артиста в хорошем качестве.

Используется исследователем как источник аватара/баннера (SPEC-КАТАЛОГ §3);
og:image SoundCloud остаётся фолбэком (app/cli/artists.py fetch-photos).
"""
import json
import urllib.parse
import urllib.request
from dataclasses import dataclass

_SEARCH_URL = "https://api.deezer.com/search/artist"
_USER_AGENT = "TGMusicBot/1.0 (https://keybest.cc)"


@dataclass
class DeezerArtist:
    id: int
    name: str
    picture_xl: str | None


def find_artist(name: str) -> DeezerArtist | None:
    """Первый результат поиска, если имя совпало без учёта регистра —
    чужое фото хуже, чем никакого."""
    query = urllib.parse.urlencode({"q": name, "limit": "3"})
    request = urllib.request.Request(
        f"{_SEARCH_URL}?{query}", headers={"User-Agent": _USER_AGENT}
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        payload = json.loads(response.read().decode("utf-8"))
    wanted = name.strip().lower()
    for item in payload.get("data", []):
        if item.get("name", "").strip().lower() == wanted:
            return DeezerArtist(
                id=item["id"], name=item["name"], picture_xl=item.get("picture_xl")
            )
    return None

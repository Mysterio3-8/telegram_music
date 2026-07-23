"""Клиент MusicBrainz (SPEC-КАТАЛОГ §3). Открытый API без ключей.

Жёсткие правила MusicBrainz: ≤1 req/sec и содержательный User-Agent —
нарушение = бан по IP. Троттлинг вшит в _get, обойти его нельзя.
Сетевые функции синхронные (CLI-исследователь работает последовательно).
"""
import json
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

MB_ROOT = "https://musicbrainz.org/ws/2"
_USER_AGENT = "TGMusicBot/1.0 (https://keybest.cc; iliyaestas@gmail.com)"
_MIN_INTERVAL_SECONDS = 1.1  # чуть больше 1 сек — запас на дрожание часов

_last_request_at = 0.0


def _get(path: str, params: dict[str, str]) -> dict:
    global _last_request_at
    wait = _MIN_INTERVAL_SECONDS - (time.monotonic() - _last_request_at)
    if wait > 0:
        time.sleep(wait)
    url = f"{MB_ROOT}/{path}?{urllib.parse.urlencode({**params, 'fmt': 'json'})}"
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    _last_request_at = time.monotonic()
    return payload


@dataclass
class ResearchedArtist:
    name: str
    mbid: str
    country: str | None = None
    aliases: list[str] = field(default_factory=list)
    genres: list[str] = field(default_factory=list)
    soundcloud_url: str | None = None
    youtube_url: str | None = None


def search_artists(query: str, limit: int = 100, offset: int = 0) -> list[dict]:
    """Поиск по Lucene-запросу MusicBrainz, например 'country:RU AND type:Person'.
    Возвращает сырые артист-словари (id, name, score, country…)."""
    payload = _get("artist", {"query": query, "limit": str(limit), "offset": str(offset)})
    return payload.get("artists", [])


def artist_details(mbid: str) -> dict:
    return _get(f"artist/{mbid}", {"inc": "genres+aliases+url-rels"})


def _extract_links(relations: list[dict]) -> tuple[str | None, str | None]:
    soundcloud = youtube = None
    for relation in relations:
        resource = (relation.get("url") or {}).get("resource", "")
        if not soundcloud and "soundcloud.com" in resource:
            soundcloud = resource
        elif not youtube and ("youtube.com" in resource or "youtu.be" in resource):
            youtube = resource
    return soundcloud, youtube


def parse_artist(details: dict) -> ResearchedArtist:
    """Сырой ответ artist_details → структура для сохранения."""
    soundcloud, youtube = _extract_links(details.get("relations", []))
    genres = [
        genre["name"].title()
        for genre in sorted(
            details.get("genres", []), key=lambda g: g.get("count", 0), reverse=True
        )[:5]
        if genre.get("name")
    ]
    aliases = sorted(
        {
            alias["name"]
            for alias in details.get("aliases", [])
            if alias.get("name") and alias["name"] != details.get("name")
        }
    )
    return ResearchedArtist(
        name=details.get("name", ""),
        mbid=details.get("id", ""),
        country=details.get("country"),
        aliases=aliases[:10],
        genres=genres,
        soundcloud_url=soundcloud,
        youtube_url=youtube,
    )

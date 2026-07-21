"""Разбор ссылок на плейлисты чужих сервисов в список «исполнитель — название».

Скачивать аудио у этих сервисов нельзя (DRM/лицензии), поэтому переносим
только МЕТАДАННЫЕ: из плейлиста достаём пары (артист, название), а сама музыка
берётся из нашей базы или догружается из открытых источников.

Источники метаданных:
- Spotify — embed-страница публичного плейлиста (JSON внутри HTML);
- Яндекс.Музыка — публичный handlers/playlist.jsx (JSON без авторизации);
- VK и всё остальное — текстовый список строками «Артист — Название».
"""
import json
import logging
import re
from dataclasses import dataclass

import aiohttp

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 20
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
)


@dataclass(frozen=True)
class TransferItem:
    artist: str
    title: str

    def query(self) -> str:
        return f"{self.artist} {self.title}".strip()


class TransferSourceError(Exception):
    """Ссылку не удалось разобрать — сообщение показывается пользователю."""


def detect_service(url: str) -> str | None:
    """spotify | yandex | vk | soundcloud — или None, если ссылка чужая."""
    text = (url or "").lower()
    if "open.spotify.com" in text or "spotify.link" in text:
        return "spotify"
    if "music.yandex." in text:
        return "yandex"
    if "vk.com" in text or "vk.ru" in text:
        return "vk"
    if "soundcloud.com" in text:
        return "soundcloud"
    return None


async def _fetch_text(url: str) -> str:
    timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url, headers={"User-Agent": BROWSER_UA}) as response:
            response.raise_for_status()
            return await response.text()


# --- Spotify ---

_SPOTIFY_ID_RE = re.compile(r"(?:playlist|album)[/:]([A-Za-z0-9]{16,})")


def _spotify_embed_url(url: str) -> str:
    match = _SPOTIFY_ID_RE.search(url)
    if not match:
        raise TransferSourceError("Не вижу id плейлиста в ссылке Spotify.")
    kind = "album" if "album" in url else "playlist"
    return f"https://open.spotify.com/embed/{kind}/{match.group(1)}"


def _walk_spotify_tracks(node, found: list[TransferItem]) -> None:
    """Структура embed-JSON меняется от релиза к релизу — ищем по форме узла."""
    if isinstance(node, dict):
        name = node.get("name")
        artists = node.get("artists")
        if isinstance(name, str) and isinstance(artists, list) and artists:
            first = artists[0]
            artist = first.get("name") if isinstance(first, dict) else None
            if isinstance(artist, str) and artist and name:
                found.append(TransferItem(artist.strip(), name.strip()))
                return
        for value in node.values():
            _walk_spotify_tracks(value, found)
    elif isinstance(node, list):
        for value in node:
            _walk_spotify_tracks(value, found)


def parse_spotify_html(html: str) -> list[TransferItem]:
    match = re.search(
        r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL
    )
    if not match:
        return []
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return []
    found: list[TransferItem] = []
    _walk_spotify_tracks(data, found)
    return dedupe(found)


async def fetch_spotify(url: str) -> list[TransferItem]:
    html = await _fetch_text(_spotify_embed_url(url))
    items = parse_spotify_html(html)
    if not items:
        raise TransferSourceError(
            "Spotify не отдал список треков. Плейлист должен быть публичным."
        )
    return items


# --- Яндекс.Музыка ---

_YANDEX_RE = re.compile(r"users/([^/]+)/playlists/(\d+)")


def yandex_api_url(url: str) -> str:
    match = _YANDEX_RE.search(url)
    if not match:
        raise TransferSourceError(
            "Нужна ссылка вида music.yandex.ru/users/<логин>/playlists/<номер>."
        )
    owner, kind = match.groups()
    return f"https://music.yandex.ru/handlers/playlist.jsx?owner={owner}&kinds={kind}"


def parse_yandex_json(payload: dict) -> list[TransferItem]:
    tracks = (payload.get("playlist") or {}).get("tracks") or []
    items: list[TransferItem] = []
    for track in tracks:
        title = (track.get("title") or "").strip()
        artists = track.get("artists") or []
        artist = (artists[0].get("name") if artists else "").strip()
        if title and artist:
            items.append(TransferItem(artist, title))
    return dedupe(items)


async def fetch_yandex(url: str) -> list[TransferItem]:
    raw = await _fetch_text(yandex_api_url(url))
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        raise TransferSourceError("Яндекс.Музыка ответила не JSON — плейлист приватный?")
    items = parse_yandex_json(payload)
    if not items:
        raise TransferSourceError("В плейлисте не нашлось треков (или он приватный).")
    return items


# --- Текстовый список (VK и любой другой сервис) ---

_TEXT_SEPARATORS = (" — ", " – ", " - ", " — ", "—", "–")


def parse_text_list(text: str) -> list[TransferItem]:
    """Строки «Артист — Название». Порядок «Название — Артист» не различить,
    поэтому договорённость одна: сначала исполнитель."""
    items: list[TransferItem] = []
    for line in (text or "").splitlines():
        line = line.strip().lstrip("0123456789.)- \t")
        if not line:
            continue
        for separator in _TEXT_SEPARATORS:
            if separator in line:
                artist, _, title = line.partition(separator)
                if artist.strip() and title.strip():
                    items.append(TransferItem(artist.strip(), title.strip()))
                break
    return dedupe(items)


def dedupe(items: list[TransferItem]) -> list[TransferItem]:
    seen: set[tuple[str, str]] = set()
    unique: list[TransferItem] = []
    for item in items:
        key = (item.artist.lower(), item.title.lower())
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


async def fetch_playlist(url: str) -> list[TransferItem]:
    """Единая точка: ссылка → список треков. Бросает TransferSourceError."""
    service = detect_service(url)
    if service == "spotify":
        return await fetch_spotify(url)
    if service == "yandex":
        return await fetch_yandex(url)
    if service == "vk":
        raise TransferSourceError(
            "ВКонтакте не отдаёт плейлисты без входа в аккаунт.\n"
            "Скопируйте список треков и пришлите текстом — строками «Артист — Название»."
        )
    raise TransferSourceError("Не узнал сервис. Поддерживаю Spotify и Яндекс.Музыку.")

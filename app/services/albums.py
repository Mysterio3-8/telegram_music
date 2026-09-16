"""Альбомы целиком: поиск по названию и полный список треков (16.09).

Владелец: «ввёл название альбома — нашёлся полный альбом, и можно выкачать по
одному треку или все 14, 24 и т.д.».

Источник — SoundCloud: `/search/albums` отвечает за 0.2–0.4 сек и знает число
треков. Замер на проде: «скриптонит 2004» → официальный «2004», 24 трека;
«kizaru born to trap» → 18; «macan» → «BRATLAND» и «I AM».

⚠️ Две особенности API, без которых фича молча ломается:
- в ответе полными приходят только первые 5 треков, остальные — заглушки с одним
  id. Их надо дозагрузить `/tracks?ids=` (до 50 за раз), иначе «альбом на 24
  трека» показывал бы пять;
- выдача полна перезаливов («M U S I C — Big Baby Tape - Dragonborn (Album)»),
  «slowed + reverb», неофициальных сборок и пустых альбомов на 0 треков.
  Решение владельца: оригиналы сверху, перезаливы ниже, мусор скрыт.

Сервис не знает о Telegram: бот и API берут отсюда одно и то же.
"""
from __future__ import annotations

import logging
import re
import threading
import time
from dataclasses import asdict, dataclass, replace

from app.services.track_lookup.ranking import Candidate, normalize_query, version_penalty

logger = logging.getLogger(__name__)

SEARCH_POOL = 20  # сколько берём у источника до фильтра — после отсева остаётся мало
MAX_TRACKS = 100  # «альбом» на 400 треков — это чья-то свалка, а не альбом
_HYDRATE_CHUNK = 50  # потолок id в одном запросе /tracks?ids=
_CACHE_TTL = 3600
_CACHE_MAX = 64

# Помечают не альбом артиста, а чужую сборку или переделку
_JUNK_MARKERS = ("unofficial", "неофициал", "fan made", "fanmade", "bootleg", "leak", "слив")
# Хвосты, которые перезаливщики дописывают к названию: «Dragonborn (Album)»,
# «2004 (Album 24.12.2019)», «Dragonborn [full album]»
_TITLE_TAIL = re.compile(
    r"\s*[\(\[]\s*(?:(?:full|полный)\s+)?(?:album|альбом|ep|lp)(?![a-zа-я])[^\)\]]*[\)\]]\s*$"
    r"|\s*[\(\[]\s*\d{2}\.\d{2}\.\d{4}[^\)\]]*[\)\]]\s*$",
    re.I,
)
# Переделки альбома. Основы слов, а не формы: «замедленный», «замедленная» и
# «замедленные» должны ловиться одинаково (прогон 16.09 пропустил
# «Born To Trap [замедленный + пространство]»).
_VERSION_STEMS = (
    "slowed", "reverb", "sped", "nightcore", "8d", "bass boost", "замедлен",
    "ускорен", "пространств", "ремикс", "remix", "cover", "karaoke", "караоке",
    "instrumental", "минус",
)
MIN_TRACKS = 2  # один трек — это сингл, а не альбом
# Латинские буквы, неотличимые от кириллицы. Официальный аккаунт Скриптонита
# пишет «Cкриптoнит» с латинскими C и o — без замены это «другой артист», и
# дубли одного альбома не схлопываются.
_HOMOGLYPHS = str.maketrans("aceopxykmthbACEOPXYKMTHB", "асеорхукмтнвАСЕОРХУКМТНВ")
_CYRILLIC = re.compile("[а-яё]", re.I)


@dataclass(frozen=True)
class AlbumCandidate:
    id: int
    title: str
    artist: str
    url: str
    track_count: int
    cover_url: str | None
    kind: str
    official: bool
    likes: int

    def as_dict(self) -> dict:
        return asdict(self)


def _split_artist_title(title: str, uploader: str) -> tuple[str, str]:
    """«Big Baby Tape - Dragonborn (Album)» у перезаливщика → (Big Baby Tape, Dragonborn).

    У официального аккаунта в названии только сам альбом («2004»), и артист — это
    аккаунт. У перезаливщика аккаунт посторонний («M U S I C»), а артист записан
    в названии через тире.
    """
    artist, album, _ = _split_with_flag(title, uploader)
    return artist, album


def _split_with_flag(title: str, uploader: str) -> tuple[str, str, bool]:
    """То же, плюс флаг «артист взят из названия, а не из имени аккаунта»."""
    cleaned = _TITLE_TAIL.sub("", title).strip()
    for dash in (" - ", " — ", " – "):
        if dash in cleaned:
            artist, _, album = cleaned.partition(dash)
            if artist.strip() and album.strip():
                return artist.strip(), _TITLE_TAIL.sub("", album).strip(), True
    return uploader.strip(), cleaned, False


def parse_album(item: dict) -> AlbumCandidate | None:
    from app.services.mojibake import repair

    title = repair((item.get("title") or "").strip())
    url = item.get("permalink_url") or ""
    album_id = item.get("id")
    if not title or not url or not album_id:
        return None
    user = item.get("user") or {}
    uploader = repair((user.get("username") or "").strip())
    artist, album_title, from_title = _split_with_flag(title, uploader)
    cover = item.get("artwork_url") or user.get("avatar_url")
    if cover:
        cover = cover.replace("-large.", "-t500x500.")
    # Официальный — верифицированный аккаунт, либо артист РАЗОБРАН из названия
    # и совпал с аккаунтом («kizaru — kizaru - BORN TO TRAP»). Имя аккаунта само
    # по себе ничего не доказывает: без тире в названии артистом становится сам
    # аккаунт, и совпадение выходит автоматическим — так «Mark Левин» с чужим
    # «Скриптонит 2004» стал бы официальным. Та же грабля, что у треков (16.08).
    official = bool(user.get("verified")) or (
        from_title and bool(uploader) and normalize_query(uploader) == normalize_query(artist)
    )
    return AlbumCandidate(
        id=int(album_id),
        title=album_title or title,
        artist=artist or uploader or "—",
        url=url,
        track_count=int(item.get("track_count") or 0),
        cover_url=cover,
        kind=(item.get("set_type") or "album").lower(),
        official=official,
        likes=int(item.get("likes_count") or 0),
    )


def _fold(text: str) -> str:
    """Ключ сравнения: латинские двойники внутри кириллического слова → кириллица."""
    words = []
    for word in (text or "").split():
        words.append(word.translate(_HOMOGLYPHS) if _CYRILLIC.search(word) else word)
    return normalize_query(" ".join(words))


def _is_version(query: str, name: str) -> bool:
    """Переделка альбома, которую не просили в запросе."""
    lowered_query, lowered_name = query.lower(), name.lower()
    # Упомянута любая переделка — человек ищет именно её, к точному слову не
    # придираемся («dragonborn slowed» должен найти «slowed + reverb»)
    if any(stem in lowered_query for stem in _VERSION_STEMS):
        return False
    return any(stem in lowered_name for stem in _VERSION_STEMS)


def _relevance(query: str, album: AlbumCandidate) -> float:
    """Доля слов запроса, найденных в «артист альбом»."""
    words = _fold(query).split()
    if not words:
        return 0.0
    haystack = _fold(f"{album.artist} {album.title}")
    return sum(1 for word in words if word in haystack) / len(words)


def rank_albums(query: str, albums: list[AlbumCandidate], limit: int = 5) -> list[AlbumCandidate]:
    """Фильтр и порядок выдачи — чистая функция, её и проверяют тесты.

    1. Пустые (0 треков) и явные сборки/переделки скрыты. Переделку оставляем,
       если её попросили в запросе («… slowed»).
    2. Дубли одного альбома схлопываются, остаётся официальный, затем самый
       залайканный.
    3. Порядок: сперва официальные, затем по совпадению с запросом, затем по лайкам.
    """
    visible: list[AlbumCandidate] = []
    for album in albums:
        if album.track_count < MIN_TRACKS:
            continue
        name = f"{album.artist} {album.title}"
        if any(marker in name.lower() for marker in _JUNK_MARKERS) and not any(m in query.lower() for m in _JUNK_MARKERS):
            continue
        if _is_version(query, name) or version_penalty(query, name) < 1.0:
            continue
        # Альбом, где не нашлось ни одного слова запроса, — посторонний: поиск
        # SoundCloud добивает выдачу чем попало («скриптонит 2004» → «NEW SCHOOL»)
        if _relevance(query, album) == 0:
            continue
        visible.append(album)

    best: dict[str, AlbumCandidate] = {}
    for album in visible:
        key = f"{_fold(album.artist)}|{_fold(album.title)}"
        current = best.get(key)
        if current is None or (album.official, album.likes) > (current.official, current.likes):
            best[key] = album

    # Сперва то, что подходит к запросу хотя бы наполовину: официальный альбом
    # ДРУГОГО названия не должен обгонять нужный перезалив. Внутри — оригиналы
    # выше, затем точность совпадения, затем лайки.
    ordered = sorted(
        best.values(),
        key=lambda a: (_relevance(query, a) >= 0.5, a.official, _relevance(query, a), a.likes),
        reverse=True,
    )
    return ordered[:limit]


def search_albums(query: str, limit: int = 5) -> list[AlbumCandidate]:
    """Альбомы по запросу. Пустой список — не нашлось или API не ответил.

    Синхронная: соединение с API общее на процесс; из асинхронного кода звать
    через asyncio.to_thread, как и поиск треков.
    """
    from app.services.soundcloud_api import api_get

    query = (query or "").strip()
    if not query:
        return []
    data = api_get("/search/albums", {"q": query, "limit": SEARCH_POOL})
    if not isinstance(data, dict):
        return []
    parsed = [parse_album(item) for item in data.get("collection") or []]
    return rank_albums(query, [album for album in parsed if album is not None], limit)


_cache: dict[int, tuple[float, list[Candidate]]] = {}
_cache_lock = threading.Lock()


def _cached(album_id: int) -> list[Candidate] | None:
    with _cache_lock:
        entry = _cache.get(album_id)
        if entry and time.monotonic() - entry[0] < _CACHE_TTL:
            return entry[1]
        return None


def _remember(album_id: int, tracks: list[Candidate]) -> None:
    with _cache_lock:
        if len(_cache) >= _CACHE_MAX:
            _cache.pop(next(iter(_cache)))  # самая старая запись
        _cache[album_id] = (time.monotonic(), tracks)


def album_tracks(album_id: int) -> list[Candidate]:
    """Все треки альбома по порядку, как кандидаты живого поиска.

    Кандидаты те же, что у обычного поиска, поэтому скачивание, минт и выдача
    переиспользуют готовую цепочку `import_candidate` — ничего своего.
    """
    from app.services.soundcloud_api import _to_candidate, api_get

    cached = _cached(album_id)
    if cached is not None:
        return cached
    data = api_get(f"/playlists/{int(album_id)}")
    if not isinstance(data, dict):
        return []
    raw = (data.get("tracks") or [])[:MAX_TRACKS]

    missing = [item["id"] for item in raw if item.get("id") and not item.get("title")]
    loaded: dict[int, dict] = {}
    for start in range(0, len(missing), _HYDRATE_CHUNK):
        chunk = missing[start : start + _HYDRATE_CHUNK]
        rows = api_get("/tracks", {"ids": ",".join(str(i) for i in chunk)})
        if isinstance(rows, list):
            loaded.update({row["id"]: row for row in rows if row.get("id")})

    album_cover = data.get("artwork_url")
    album_artist = ((data.get("user") or {}).get("username") or "").strip()
    tracks: list[Candidate] = []
    for item in raw:
        full = item if item.get("title") else loaded.get(item.get("id"))
        if not full:
            continue  # трек удалён или закрыт — пропускаем, а не рвём весь альбом
        candidate = _to_candidate(full)
        if candidate is None:
            continue
        # Candidate неизменяемый — дополняем копией
        if not candidate.cover_url and album_cover:
            candidate = replace(candidate, cover_url=album_cover)
        if not candidate.artist and album_artist:
            candidate = replace(candidate, artist=album_artist)
        tracks.append(candidate)

    if tracks:
        _remember(album_id, tracks)
    return tracks


# --- Один альбом за раз на человека -------------------------------------------
# Альбом на 24 трека — это ~5 минут работы воркера. Без замка десять нажатий
# «скачать весь» ставили бы десять одинаковых выкачек, и очередь стояла у всех.

_LOCK_PREFIX = "album:active:"
_LOCK_TTL_SECONDS = 45 * 60  # с запасом больше самого длинного альбома; дальше истечёт сам


def _redis_sync():
    from app.config import settings

    if not settings.redis_url:
        return None
    try:
        import redis

        return redis.from_url(settings.redis_url)
    except Exception:  # noqa: BLE001 — замок опционален, как и кэш поиска
        logger.warning("Альбомы: Redis недоступен, замок не ставится", exc_info=True)
        return None


def acquire_album_lock(telegram_id: int) -> bool:
    """True — можно начинать. Redis недоступен → не блокируем: выкачка важнее замка."""
    client = _redis_sync()
    if client is None:
        return True
    try:
        return bool(client.set(f"{_LOCK_PREFIX}{telegram_id}", "1", nx=True, ex=_LOCK_TTL_SECONDS))
    except Exception:  # noqa: BLE001
        logger.warning("Альбомы: не удалось поставить замок", exc_info=True)
        return True


def release_album_lock(telegram_id: int) -> None:
    client = _redis_sync()
    if client is None:
        return
    try:
        client.delete(f"{_LOCK_PREFIX}{telegram_id}")
    except Exception:  # noqa: BLE001 — истечёт сам по TTL
        logger.warning("Альбомы: не удалось снять замок", exc_info=True)


def estimate_minutes(track_count: int) -> int:
    """Грубая оценка для человека: ~12 сек на трек (скачивание + пауза отправки)."""
    return max(1, -(-track_count * 12 // 60))

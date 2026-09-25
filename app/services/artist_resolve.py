"""Нормальные имена и фото для артистов, которых каталог не узнавал (22.09).

Владелец: «правильно надо запарсить артистов, нормальные имена дать им,
правильные фотки… загрузить туда все треки».

Замер прода 24.09: 2907 треков из 8547 (34%) не привязаны к артисту вовсе, и
первым в списке стоит «ChiefKeef» — 559 треков без карточки. Причины три, и
каждая лечится своим способом:

1. Артиста просто нет в таблице `artists` (Chief Keef, A$AP Rocky, MACAN…) —
   мировой обход MusicBrainz шёл по странам и до них не дошёл.
2. Имя — ник загрузчика с SoundCloud: «ChiefKeef», «playboicarti»,
   «smokepurpp (Purpp)», «unki (@unkiplug)». Настоящее имя у них то же самое
   без пробелов и регистра — «chiefkeef» == «Chief Keef», — поэтому сверяем
   по «сжатому» ключу и берём каноническое написание у Deezer.
3. Дуэт: «Miyagi & Эндшпиль», «Artik & Anna Asti». Трек идёт к первому артисту
   — так же поступают Spotify и Яндекс.

⚠️ `tracks.artist` мы НЕ переписываем: это строка из файла и основа поиска и
дедупа, массовое переименование сломало бы оба. Правильное имя живёт в
карточке артиста, а исходная строка ложится в её алиасы — так и старые, и
новые треки с тем же ником сами найдут дорогу к карточке.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Artist, Track
from app.services.artist_entities import normalize_name

logger = logging.getLogger(__name__)

# Меньше — это шум: разовая перезаливка, опечатка. Карточка артиста с одним
# треком хуже, чем её отсутствие.
MIN_TRACKS = 3
# Насколько имя Deezer может отличаться от нашего по сжатому ключу. Выше
# нельзя: «Maksim Dark» против «МакSим» — тот самый урок прогрева 21.09.
SIMILAR_ENOUGH = 0.9

_PARENS = re.compile(r"\s*[\(\[][^)\]]*[\)\]]\s*")
_DUET = re.compile(r"\s+(?:&|x|х|feat\.?|ft\.?|vs\.?)\s+|,\s*", re.IGNORECASE)
_COMPACT = re.compile(r"[^0-9a-zа-я$]+")


def clean_name(raw: str) -> str:
    """Убирает хвосты загрузчика: «(Purpp)», «(@unkiplug)», «(Gorky Park)»."""
    name = _PARENS.sub(" ", raw or "").strip()
    return re.sub(r"\s{2,}", " ", name) or (raw or "").strip()


def primary_artist(raw: str) -> str:
    """Главный артист строки: до первого «&», «feat», «x» или запятой."""
    cleaned = clean_name(raw)
    head = _DUET.split(cleaned, maxsplit=1)[0].strip()
    return head or cleaned


def compact(name: str) -> str:
    """Ключ без пробелов, регистра и знаков: «Chief Keef» == «ChiefKeef»."""
    return _COMPACT.sub("", (name or "").lower().replace("ё", "е"))


def same_artist(ours: str, theirs: str) -> bool:
    a, b = compact(ours), compact(theirs)
    if len(a) < 2 or len(b) < 2:
        return False
    if a == b:
        return True
    return SequenceMatcher(None, a, b).ratio() >= SIMILAR_ENOUGH


@dataclass
class ResolveReport:
    bound_existing: int = 0  # нашли готовую карточку, просто привязали
    created_with_photo: int = 0  # новая карточка с фото и именем Deezer
    created_plain: int = 0  # новая карточка без фото (Deezer не знает)
    tracks_bound: int = 0
    skipped: int = 0


async def unbound_names(session: AsyncSession, limit: int) -> list[tuple[str, int]]:
    """Строки артистов без привязки, самые массовые первыми."""
    rows = await session.execute(
        select(Track.artist, func.count().label("n"))
        .where(Track.artist_id.is_(None), Track.artist.is_not(None), Track.artist != "")
        .group_by(Track.artist)
        .having(func.count() >= MIN_TRACKS)
        .order_by(func.count().desc())
        .limit(limit)
    )
    return [(name, count) for name, count in rows.all()]


async def _existing_by_compact(session: AsyncSession, name: str) -> Artist | None:
    """Готовая карточка с тем же именем — точно или по сжатому ключу."""
    exact = await session.scalar(
        select(Artist).where(Artist.normalized_name == normalize_name(name)).limit(1)
    )
    if exact is not None:
        return exact
    key = compact(name)
    if len(key) < 3:
        return None
    # Сжатый ключ в базе не хранится, поэтому кандидатов отбираем по первой
    # букве — это отсекает почти всю таблицу до сравнения в Питоне.
    # ⚠️ SQLite lower() не понижает кириллицу, поэтому сравниваем обе формы.
    first = normalize_name(name)[:1]
    candidates = (
        await session.scalars(
            select(Artist)
            .where(
                (Artist.normalized_name.like(f"{first}%"))
                | (Artist.normalized_name.like(f"{first.upper()}%"))
            )
            .limit(5000)
        )
    ).all()
    for artist in candidates:
        if compact(artist.name) == key:
            return artist
    return None


def _add_alias(artist: Artist, alias: str) -> None:
    try:
        aliases = json.loads(artist.aliases) if artist.aliases else []
    except (TypeError, ValueError):
        aliases = []
    if alias not in aliases and normalize_name(alias) != artist.normalized_name:
        aliases.append(alias)
        artist.aliases = json.dumps(aliases, ensure_ascii=False)


async def _bind(session: AsyncSession, raw: str, artist_id: int) -> int:
    result = await session.execute(
        update(Track)
        .where(Track.artist == raw, Track.artist_id.is_(None))
        .values(artist_id=artist_id)
    )
    return result.rowcount or 0


def deezer_lookup(name: str) -> dict | None:
    """Каноническое имя и фото. Сеть и формат Deezer — не наша ответственность:
    при любой ошибке карточка просто заводится без фото."""
    import urllib.parse
    import urllib.request

    query = urllib.parse.urlencode({"q": name, "limit": "5"})
    request = urllib.request.Request(
        f"https://api.deezer.com/search/artist?{query}",
        headers={"User-Agent": "TGMusicBot/1.0 (https://t.me/muz_damn_bot)"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:  # noqa: BLE001
        logger.warning("Deezer не ответил на «%s»", name, exc_info=True)
        return None
    for item in payload.get("data") or []:
        if same_artist(name, item.get("name") or ""):
            return item
    return None


async def resolve_unbound(
    session: AsyncSession, limit: int = 50, lookup=deezer_lookup
) -> ResolveReport:
    """Главный проход: каждой массовой непривязанной строке — карточку."""
    report = ResolveReport()
    for raw, _count in await unbound_names(session, limit):
        main = primary_artist(raw)
        if len(compact(main)) < 2:
            report.skipped += 1
            continue

        artist = await _existing_by_compact(session, main)
        if artist is None:
            found = lookup(main)
            if found:
                # Deezer мог уже попасть в базу под своим написанием — не плодим дубль
                artist = await _existing_by_compact(session, found.get("name") or "")
            if artist is None:
                name = (found or {}).get("name") or main
                artist = Artist(
                    name=name,
                    normalized_name=normalize_name(name),
                    photo_url=(found or {}).get("picture_xl") or None,
                    deezer_id=(found or {}).get("id"),
                )
                session.add(artist)
                await session.flush()
                if artist.photo_url:
                    report.created_with_photo += 1
                else:
                    report.created_plain += 1
            else:
                report.bound_existing += 1
                if found and not artist.photo_url and found.get("picture_xl"):
                    artist.photo_url = found["picture_xl"]
        else:
            report.bound_existing += 1
        _add_alias(artist, raw)
        report.tracks_bound += await _bind(session, raw, artist.id)
        await session.commit()
    return report

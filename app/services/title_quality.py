"""Определение «не-музыкальных» названий (видеоклипы, премьеры, реакции).

Такие записи попадают в базу, когда вместо аудио скачивается видео. В Infinity Mix
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
    # Не-музыкальный YouTube: запрос «секс» приносил ролики про игрушки и биологию.
    # Ловим формат ролика, а не тему — темы фильтровать нельзя, в песнях бывает всё.
    r"интервью",
    r"подкаст",
    r"podcast",
    r"лекци[яи]",
    r"документальн\w*",
    r"влог",
    r"vlog",
    r"стрим",
    r"гайд",
    r"туториал",
    r"tutorial",
    r"распаковк\w*",
    r"unboxing",
    r"как\s+(?:это\s+)?(?:работает|устроен\w*|выбрать|сделать)",
    r"что\s+такое",
    r"почему",
    r"топ[-\s]?\d+",
    # Кино и сериалы: «Sex/Life — Official Teaser» проходил фильтр формы,
    # потому что тире в названии есть, а музыкой он не является
    r"teaser",
    r"тизер",
    r"sneak\s+peek",
    r"season\s*\d*",
    r"сезон",
    r"seri[ea]s",
    r"эпизод",
    r"episode",
    r"s\d+e\d+",
)

# Биты и болванки для рэперов. Их на SoundCloud больше, чем самих треков, и по
# запросу «Драгонборн» половина выдачи была «LIL PUMP x PHARAON x BIG BABY TAPE
# TYPE BEAT» и «[FREE] ... x LIL KRYSTALLL». Формально это музыка, поэтому в
# общий мусор их класть нельзя — человек, ищущий бит, должен его найти. Но если
# он бита не просил, такие записи обязаны стоять ПОСЛЕ настоящих треков.
_BEAT_MARKERS = (
    r"type\s*beat",
    r"free\s*beat",
    r"\[\s*free\s*\]",
    r"\(\s*free\s*\)",
    r"минус\w*",
    r"instrumental",
    r"инструментал\w*",
    r"фристайл",
    r"freestyle",
    r"мэшап",
    r"mashup",
    r"бит\s+для",
)

_BEAT_RE = re.compile("|".join(_BEAT_MARKERS), re.IGNORECASE)


def is_beat_or_instrumental(title: str) -> bool:
    """True — это бит, минус, фристайл или мэшап, а не авторский трек."""
    return bool(title) and bool(_BEAT_RE.search(title))

_JUNK_RE = re.compile(r"(?:^|[\s\(\[\|/–—-])(?:" + "|".join(_JUNK_MARKERS) + r")(?:$|[\s\)\]\|/–—-])", re.IGNORECASE)


def is_probably_junk(title: str) -> bool:
    """True — название похоже на видео/промо, а не на музыкальный трек."""
    if not title:
        return False
    return bool(_JUNK_RE.search(title))

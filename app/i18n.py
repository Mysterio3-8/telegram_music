"""Мультиязычность бота и Mini App — заготовка (запрос владельца).

Полностью переведены русский и английский. Ещё пять популярных языков заведены
пустыми словарями: они уже выбираются в интерфейсе, но текст пока показывается
на английском. Чтобы включить язык по-настоящему, достаточно наполнить его
словарь — трогать код не нужно.

Цепочка выбора текста: выбранный язык → английский → русский → сам ключ.
Русский последний, потому что он полный: до ключа дело дойти не должно.

Язык пользователя: `users.ui_language` (осознанный выбор) важнее
`users.language` (код из профиля Telegram, обновляется на каждом /start).
"""
from dataclasses import dataclass

DEFAULT_LANGUAGE = "ru"
FALLBACK_LANGUAGE = "en"


@dataclass(frozen=True)
class Language:
    code: str
    title: str  # самоназвание — в списке выбора язык должен быть узнаваем
    flag: str


LANGUAGES: tuple[Language, ...] = (
    Language("ru", "Русский", "🇷🇺"),
    Language("en", "English", "🇬🇧"),
    Language("es", "Español", "🇪🇸"),
    Language("de", "Deutsch", "🇩🇪"),
    Language("fr", "Français", "🇫🇷"),
    Language("pt", "Português", "🇵🇹"),
    Language("tr", "Türkçe", "🇹🇷"),
)

LANGUAGE_CODES: frozenset[str] = frozenset(item.code for item in LANGUAGES)

# Языки без перевода: интерфейс на английском, пока словарь пуст
TRANSLATIONS: dict[str, dict[str, str]] = {
    "ru": {
        "cabinet.greeting": "👋 Привет, <b>{name}</b> · ID: <code>{telegram_id}</code>",
        "cabinet.premium_until": "💎 Premium до {date}",
        "cabinet.free_plan": "Бесплатный тариф",
        "cabinet.library": "🎵 В библиотеке: {count} {tracks_word}",
        "cabinet.hint": (
            "Просто отправьте название песни, исполнителя в чат этого бота — "
            "я моментально найду нужный трек."
        ),
        "cabinet.player_title": "🎧 <b>Открыть плеер</b>",
        "cabinet.player_pitch": (
            "Полноценный музыкальный сервис как VK или Apple Music: миксы, плейлисты, "
            "тексты песен, эквалайзер и офлайн-режим. Удобнее и лучше чем другие сервисы."
        ),
        "cabinet.price": "💎 {price} ₽/месяц • Первый день бесплатно и рефералки в боте и Mini App",
        "menu.player": "🎧 Открыть плеер",
        "menu.upload": "⬆️ Загрузить трек",
        "menu.premium": "💎 Открыть плеер — {price} ₽/мес",
        "menu.referral": "🎁 Реферальная программа",
        "menu.support": "🆘 Поддержка / жалобы / идеи",
        "menu.language": "🌍 Язык · Language",
        "lang.title": "🌍 <b>Язык интерфейса</b>\n\nВыберите язык — он сохранится за вами.",
        "lang.saved": "Язык сохранён",
        "lang.pending": (
            "Перевод на этот язык ещё готовится — пока интерфейс будет на английском."
        ),
        "lang.back": "⬅️ Назад",
        "tracks.one": "трек",
        "tracks.few": "трека",
        "tracks.many": "треков",
    },
    "en": {
        "cabinet.greeting": "👋 Hi, <b>{name}</b> · ID: <code>{telegram_id}</code>",
        "cabinet.premium_until": "💎 Premium until {date}",
        "cabinet.free_plan": "Free plan",
        "cabinet.library": "🎵 In your library: {count} {tracks_word}",
        "cabinet.hint": (
            "Just send a song title or an artist to this chat — "
            "I'll find the track right away."
        ),
        "cabinet.player_title": "🎧 <b>Open the player</b>",
        "cabinet.player_pitch": (
            "A full music service like VK or Apple Music: mixes, playlists, "
            "lyrics, an equalizer and offline mode."
        ),
        "cabinet.price": "💎 {price} ₽/month • First day free, plus referrals in the bot and Mini App",
        "menu.player": "🎧 Open the player",
        "menu.upload": "⬆️ Upload a track",
        "menu.premium": "💎 Open the player — {price} ₽/mo",
        "menu.referral": "🎁 Referral program",
        "menu.support": "🆘 Support / reports / ideas",
        "menu.language": "🌍 Язык · Language",
        "lang.title": "🌍 <b>Interface language</b>\n\nPick a language — we'll remember it.",
        "lang.saved": "Language saved",
        "lang.pending": "This language isn't translated yet — the interface stays in English.",
        "lang.back": "⬅️ Back",
        "tracks.one": "track",
        "tracks.few": "tracks",
        "tracks.many": "tracks",
    },
    "es": {},
    "de": {},
    "fr": {},
    "pt": {},
    "tr": {},
}


def is_translated(code: str) -> bool:
    """Есть ли у языка собственный перевод (иначе показываем английский)."""
    return bool(TRANSLATIONS.get(code))


def normalize_language(code: str | None) -> str:
    """Код Telegram («en-US», «pt-BR») → поддерживаемый язык. Неизвестный → русский."""
    if not code:
        return DEFAULT_LANGUAGE
    base = code.split("-")[0].lower()
    return base if base in LANGUAGE_CODES else DEFAULT_LANGUAGE


def t(key: str, lang: str = DEFAULT_LANGUAGE, **kwargs) -> str:
    """Строка по ключу. Непереведённый язык падает на английский, затем на русский."""
    for candidate in (lang, FALLBACK_LANGUAGE, DEFAULT_LANGUAGE):
        text = TRANSLATIONS.get(candidate, {}).get(key)
        if text is not None:
            return text.format(**kwargs) if kwargs else text
    return key


def tracks_word(count: int, lang: str = DEFAULT_LANGUAGE) -> str:
    """Слово «трек» в нужном числе. Русский требует трёх форм, английский — двух."""
    if normalize_language(lang) == "ru":
        if count % 10 == 1 and count % 100 != 11:
            return t("tracks.one", lang)
        if count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14):
            return t("tracks.few", lang)
        return t("tracks.many", lang)
    return t("tracks.one" if count == 1 else "tracks.many", lang)

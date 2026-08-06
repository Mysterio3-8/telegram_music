"""Мультиязычность бота и Mini App.

Словари живут по одному файлу на язык в `locales/` — так их правит переводчик,
не читая остальные шесть. Цепочка выбора текста: выбранный язык → английский →
русский → сам ключ. Русский последний, потому что он полный: до ключа дело
дойти не должно.

Язык пользователя: `users.ui_language` (осознанный выбор) важнее
`users.language` (код устройства из Telegram, обновляется на каждом /start).
Разрешает язык мидлварь `app.middlewares.i18n` и кладёт его в `lang` — хендлеру
достаточно объявить этот параметр.
"""
from contextvars import ContextVar
from dataclasses import dataclass

from app.i18n.locales import de, en, es, fr, pt, ru, tr

DEFAULT_LANGUAGE = "ru"
FALLBACK_LANGUAGE = "en"

# Язык текущего апдейта. ContextVar, а не глобальная переменная: у каждой
# корутины своё значение, поэтому параллельные апдейты не путают языки.
_current_language: ContextVar[str] = ContextVar("ui_language", default=DEFAULT_LANGUAGE)


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

TRANSLATIONS: dict[str, dict[str, str]] = {
    "ru": ru.MESSAGES,
    "en": en.MESSAGES,
    "es": es.MESSAGES,
    "de": de.MESSAGES,
    "fr": fr.MESSAGES,
    "pt": pt.MESSAGES,
    "tr": tr.MESSAGES,
}

# Языки, которых у нас нет, но для которых русский — куда более вероятный
# родной, чем английский. Всё остальное незнакомое уходит на английский:
# японцу или поляку русский интерфейс поможет меньше, чем международный.
RUSSIAN_NEIGHBOUR_LOCALES: frozenset[str] = frozenset(
    {"uk", "be", "kk", "uz", "ky", "tg", "tk", "az", "hy", "ka", "mn"}
)


def is_translated(code: str) -> bool:
    """Есть ли у языка собственный перевод (иначе показываем английский)."""
    return bool(TRANSLATIONS.get(code))


def normalize_language(code: str | None) -> str:
    """Код языка устройства («en-US», «pt-BR») → язык интерфейса.

    Telegram присылает язык клиента в `language_code`, то есть по факту язык
    телефона. Незнакомый язык уводим в английский, а соседние с русским — в
    русский. Пустой код — это «Telegram ничего не сказал», тут вернее ставка на
    ядро аудитории, а не на английский."""
    if not code:
        return DEFAULT_LANGUAGE
    base = code.split("-")[0].lower()
    if base in LANGUAGE_CODES:
        return base
    if base in RUSSIAN_NEIGHBOUR_LOCALES:
        return DEFAULT_LANGUAGE
    return FALLBACK_LANGUAGE


def set_current_language(code: str | None) -> str:
    """Запоминает язык текущего апдейта. Ставит мидлварь, читает t() по умолчанию."""
    resolved = normalize_language(code)
    _current_language.set(resolved)
    return resolved


def get_current_language() -> str:
    return _current_language.get()


def t(key: str, lang: str | None = None, **kwargs) -> str:
    """Строка по ключу. Непереведённый язык падает на английский, затем на русский.

    Без явного `lang` берётся язык текущего апдейта — так экраны и клавиатуры
    не тянут его через свои сигнатуры. Вне обработки апдейта (Celery, старый
    бот-указатель) язык передаётся параметром."""
    lang = lang or _current_language.get()
    for candidate in (lang, FALLBACK_LANGUAGE, DEFAULT_LANGUAGE):
        text = TRANSLATIONS.get(candidate, {}).get(key)
        if text is not None:
            return text.format(**kwargs) if kwargs else text
    return key


def plural(base_key: str, count: int, lang: str | None = None) -> str:
    """Слово в нужном числе: `<base>.one` / `.few` / `.many`.

    Русскому нужны три формы (трек / трека / треков), остальным языкам хватает
    двух — они берут `.one` и `.many`, а `.few` просто не заводят."""
    lang = lang or _current_language.get()
    if normalize_language(lang) == DEFAULT_LANGUAGE:
        if count % 10 == 1 and count % 100 != 11:
            return t(f"{base_key}.one", lang)
        if count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14):
            return t(f"{base_key}.few", lang)
        return t(f"{base_key}.many", lang)
    return t(f"{base_key}.one" if count == 1 else f"{base_key}.many", lang)


def tracks_word(count: int, lang: str | None = None) -> str:
    return plural("word.tracks", count, lang)

// Мультиязычность Mini App — заготовка, зеркало app/i18n.py.
//
// Переведены русский и английский. Остальные языки уже выбираются, но пока
// показывают английский: чтобы включить язык, достаточно наполнить его словарь.
// Цепочка: выбранный язык → английский → русский → сам ключ.
//
// Выбор хранится на сервере (users.ui_language), поэтому бот и приложение
// всегда говорят с человеком на одном языке.

export const DEFAULT_LANGUAGE = "ru";
export const FALLBACK_LANGUAGE = "en";

export const LANGUAGES = [
  { code: "ru", title: "Русский", flag: "🇷🇺" },
  { code: "en", title: "English", flag: "🇬🇧" },
  { code: "es", title: "Español", flag: "🇪🇸" },
  { code: "de", title: "Deutsch", flag: "🇩🇪" },
  { code: "fr", title: "Français", flag: "🇫🇷" },
  { code: "pt", title: "Português", flag: "🇵🇹" },
  { code: "tr", title: "Türkçe", flag: "🇹🇷" },
];

const TRANSLATIONS = {
  ru: {
    "nav.home": "Главная",
    "nav.search": "Поиск",
    "nav.library": "Моя музыка",
    "nav.profile": "Профиль",
    "settings.title": "Настройки",
    "settings.section.music": "Музыка",
    "settings.section.app": "Приложение",
    "settings.section.subscription": "Подписка",
    "settings.section.help": "Помощь",
    "settings.section.docs": "Документы",
    "settings.language": "Язык · Language",
    "language.title": "Язык интерфейса",
    "language.hint": "Язык сохранится и в боте, и в приложении.",
    "language.pending": "Перевод готовится — пока интерфейс будет на английском.",
    "common.back": "Назад",
  },
  en: {
    "nav.home": "Home",
    "nav.search": "Search",
    "nav.library": "My music",
    "nav.profile": "Profile",
    "settings.title": "Settings",
    "settings.section.music": "Music",
    "settings.section.app": "App",
    "settings.section.subscription": "Subscription",
    "settings.section.help": "Help",
    "settings.section.docs": "Documents",
    "settings.language": "Язык · Language",
    "language.title": "Interface language",
    "language.hint": "The language applies to both the bot and the app.",
    "language.pending": "Translation is on the way — the interface stays in English.",
    "common.back": "Back",
  },
  es: {},
  de: {},
  fr: {},
  pt: {},
  tr: {},
};

const SUPPORTED = new Set(LANGUAGES.map((item) => item.code));

// Языки без своего перевода, для которых русский вероятнее английского.
// Список обязан совпадать с RUSSIAN_NEIGHBOUR_LOCALES в app/i18n.py, иначе бот и
// приложение определят язык по-разному.
const RUSSIAN_NEIGHBOURS = new Set([
  "uk", "be", "kk", "uz", "ky", "tg", "tk", "az", "hy", "ka", "mn",
]);

let current = DEFAULT_LANGUAGE;

export function normalizeLanguage(code) {
  if (!code) return DEFAULT_LANGUAGE;
  const base = String(code).split("-")[0].toLowerCase();
  if (SUPPORTED.has(base)) return base;
  return RUSSIAN_NEIGHBOURS.has(base) ? DEFAULT_LANGUAGE : FALLBACK_LANGUAGE;
}

export function isTranslated(code) {
  return Object.keys(TRANSLATIONS[code] || {}).length > 0;
}

export function setLanguage(code) {
  current = normalizeLanguage(code);
  document.documentElement.lang = current;
  return current;
}

export function getLanguage() {
  return current;
}

export function t(key, vars) {
  for (const candidate of [current, FALLBACK_LANGUAGE, DEFAULT_LANGUAGE]) {
    const text = (TRANSLATIONS[candidate] || {})[key];
    if (text === undefined) continue;
    if (!vars) return text;
    return text.replace(/\{(\w+)\}/g, (match, name) =>
      vars[name] === undefined ? match : vars[name],
    );
  }
  return key;
}

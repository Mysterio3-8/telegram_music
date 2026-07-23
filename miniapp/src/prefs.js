// Локальные предпочтения пользователя (localStorage). Сервер о них пока не знает —
// это клиентский слой: недавние треки, недавние поисковые запросы, настройки
// рекомендаций (настроение/тип/язык). Реальная фильтрация рекомендаций на сервере —
// следующий блок; здесь честно сохраняем выбор и историю.

const RECENT_TRACKS_KEY = "tgmusic-recent-tracks";
const RECENT_SEARCHES_KEY = "tgmusic-recent-searches";
const REC_SETTINGS_KEY = "tgmusic-rec-settings";
const FAV_ARTISTS_KEY = "tgmusic-fav-artists";

const RECENT_TRACKS_LIMIT = 20;
const RECENT_SEARCHES_LIMIT = 10;

function readJson(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch {
    return fallback;
  }
}

function writeJson(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // приватный режим / переполнение — не роняем приложение
  }
}

// ---------- Недавно прослушанные ----------

export function getRecentTracks() {
  return readJson(RECENT_TRACKS_KEY, []);
}

export function pushRecentTrack(track) {
  if (!track) return;
  // audio_url НЕ сохраняем: подписанная ссылка живёт 6 часов, протухшая копия
  // в localStorage давала «трек недоступен». Плеер резолвит свежую по id.
  const slim = {
    id: track.id,
    title: track.title,
    artist: track.artist,
    duration: track.duration,
  };
  const rest = getRecentTracks().filter((t) => t.id !== track.id);
  writeJson(RECENT_TRACKS_KEY, [slim, ...rest].slice(0, RECENT_TRACKS_LIMIT));
}

// ---------- Недавние поисковые запросы ----------

export function getRecentSearches() {
  return readJson(RECENT_SEARCHES_KEY, []);
}

export function pushRecentSearch(query) {
  const value = query.trim();
  if (!value) return;
  const rest = getRecentSearches().filter((q) => q.toLowerCase() !== value.toLowerCase());
  writeJson(RECENT_SEARCHES_KEY, [value, ...rest].slice(0, RECENT_SEARCHES_LIMIT));
}

export function clearRecentSearches() {
  writeJson(RECENT_SEARCHES_KEY, []);
}

// ---------- Настройки рекомендаций ----------

const DEFAULT_REC_SETTINGS = { mood: "", recognizability: "", language: "" };

export function getRecSettings() {
  return { ...DEFAULT_REC_SETTINGS, ...readJson(REC_SETTINGS_KEY, {}) };
}

export function saveRecSettings(settings) {
  writeJson(REC_SETTINGS_KEY, { ...DEFAULT_REC_SETTINGS, ...settings });
}

export function clearRecSettings() {
  writeJson(REC_SETTINGS_KEY, { ...DEFAULT_REC_SETTINGS });
}

export function hasRecSettings() {
  const s = getRecSettings();
  return Boolean(s.mood || s.recognizability || s.language);
}

// ---------- Онбординг (показывается один раз при первом входе) ----------
// localStorage в Telegram-вебвью не везде переживает перезапуск, поэтому флаг
// дублируется в Telegram CloudStorage (живёт на сервере Telegram, привязан к юзеру).

const ONBOARDED_KEY = "tgmusic-onboarded";

function cloudStorage() {
  const tg = typeof window !== "undefined" && window.Telegram && window.Telegram.WebApp;
  return tg && tg.CloudStorage && typeof tg.CloudStorage.getItem === "function"
    ? tg.CloudStorage.getItem && tg.CloudStorage
    : null;
}

export function isOnboarded() {
  try {
    return localStorage.getItem(ONBOARDED_KEY) === "1";
  } catch {
    return true; // приватный режим — не мучаем онбордингом
  }
}

export function setOnboarded() {
  writeJson(ONBOARDED_KEY, 1);
  const cloud = cloudStorage();
  if (cloud) {
    try {
      cloud.setItem(ONBOARDED_KEY, "1", () => {});
    } catch {
      // CloudStorage недоступен — остаёмся на localStorage
    }
  }
}

// Проверка облачного флага (после переустановки/чистки localStorage).
// Резолвится максимум через секунду — онбординг не должен ждать сеть вечно.
export function isOnboardedCloud() {
  const cloud = cloudStorage();
  if (!cloud) return Promise.resolve(false);
  return new Promise((resolve) => {
    const timer = setTimeout(() => resolve(false), 1000);
    try {
      cloud.getItem(ONBOARDED_KEY, (err, value) => {
        clearTimeout(timer);
        resolve(!err && value === "1");
      });
    } catch {
      clearTimeout(timer);
      resolve(false);
    }
  });
}

// ---------- Настройки интерфейса (акцентный цвет, тактильный отклик) ----------

const UI_SETTINGS_KEY = "tgmusic-ui-settings";
const DEFAULT_UI_SETTINGS = { accent: "blue", haptic: true };

export function getUiSettings() {
  return { ...DEFAULT_UI_SETTINGS, ...readJson(UI_SETTINGS_KEY, {}) };
}

export function saveUiSettings(settings) {
  writeJson(UI_SETTINGS_KEY, { ...DEFAULT_UI_SETTINGS, ...settings });
}

// Применить акцент к документу: [data-accent] переопределяет токены (tokens.css)
export function applyAccent(accent = getUiSettings().accent) {
  if (typeof document === "undefined") return;
  if (accent && accent !== "blue") {
    document.documentElement.dataset.accent = accent;
  } else {
    delete document.documentElement.dataset.accent;
  }
}

// ---------- Любимые исполнители (предпочтения) ----------

export function getFavoriteArtists() {
  return readJson(FAV_ARTISTS_KEY, []);
}

export function isFavoriteArtist(artist) {
  return getFavoriteArtists().some((a) => a.toLowerCase() === artist.toLowerCase());
}

export function toggleFavoriteArtist(artist) {
  const value = (artist || "").trim();
  if (!value) return;
  const current = getFavoriteArtists();
  const exists = current.some((a) => a.toLowerCase() === value.toLowerCase());
  const next = exists
    ? current.filter((a) => a.toLowerCase() !== value.toLowerCase())
    : [value, ...current];
  writeJson(FAV_ARTISTS_KEY, next);
}

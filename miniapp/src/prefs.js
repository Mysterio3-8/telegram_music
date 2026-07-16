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
  const slim = {
    id: track.id,
    title: track.title,
    artist: track.artist,
    duration: track.duration,
    audio_url: track.audio_url,
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

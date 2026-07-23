// Реальный API-клиент: JWT по Telegram WebApp initData, никаких моков.
// В проде mini app и API живут на одном домене (nginx: /api → uvicorn).
// В dev (порт 5500, python http.server) API поднимается отдельно на 8010.

const IS_DEV = location.port === "5500";
export const API_BASE = IS_DEV ? "http://127.0.0.1:8010" : "/api";

let accessToken = null;

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

function tg() {
  return window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
}

export function telegramUser() {
  const webApp = tg();
  return webApp && webApp.initDataUnsafe ? webApp.initDataUnsafe.user || null : null;
}

export async function login() {
  // Dev-режим: токен кладётся в localStorage вручную (сгенерирован локальным секретом)
  const devToken = IS_DEV ? localStorage.getItem("tgmusic-dev-token") : null;
  if (devToken) {
    accessToken = devToken;
    return;
  }
  const webApp = tg();
  const initData = webApp ? webApp.initData : "";
  if (!initData) {
    throw new ApiError("Откройте приложение из Telegram", 401);
  }
  const response = await fetch(`${API_BASE}/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ init_data: initData }),
  });
  if (!response.ok) {
    throw new ApiError("Не удалось войти", response.status);
  }
  const data = await response.json();
  accessToken = data.access_token;
}

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      Authorization: `Bearer ${accessToken}`,
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...(options.headers || {}),
    },
  });
  if (response.status === 401 && !options._retried) {
    // токен истёк — перелогин и РОВНО один повтор (иначе бесконечный цикл 401)
    await login();
    return request(path, { ...options, _retried: true });
  }
  if (!response.ok) {
    // Текст ошибки от сервера полезнее кода: «плейлист приватный», «нет брокера» и т.п.
    const detail = await response
      .json()
      .then((body) => (typeof body.detail === "string" ? body.detail : ""))
      .catch(() => "");
    throw new ApiError(detail || `Ошибка запроса (${response.status})`, response.status);
  }
  if (response.status === 204) return null;
  return response.json();
}

export function resolveAudioUrl(track) {
  return track.audio_url ? `${API_BASE}${track.audio_url}` : null;
}

export function getTracks(query = "", page = 1, pageSize = 100) {
  const params = new URLSearchParams({ q: query, page: String(page), page_size: String(pageSize) });
  return request(`/tracks?${params}`);
}

// Свежий трек по id (минус — отрицательный id): даёт новую подписанную audio_url,
// когда кэшированная протухла (TTL 6 часов) или её нет вовсе (треки из «Недавних»).
export function getTrackById(trackId) {
  return request(`/track/${trackId}`);
}

// Минусы: приходят в формате треков с отрицательными id (вкладка «Минусы» в поиске)
export function getInstrumentals(query = "", page = 1, pageSize = 50) {
  const params = new URLSearchParams({ q: query, page: String(page), page_size: String(pageSize) });
  return request(`/instrumentals?${params}`);
}

export function getLibrary(page = 1, pageSize = 100) {
  return request(`/library?page=${page}&page_size=${pageSize}`);
}

export function getLibraryIds() {
  return request("/library/ids");
}

export function addToLibrary(trackId) {
  return request(`/library/${trackId}`, { method: "POST" });
}

export function removeFromLibrary(trackId) {
  return request(`/library/${trackId}`, { method: "DELETE" });
}

export function getPremiumStatus() {
  return request("/premium/status");
}

export function getProfile() {
  return request("/profile");
}

export function getMix({ mood, recognizability, language } = {}) {
  const params = new URLSearchParams();
  if (mood) params.set("mood", mood);
  if (recognizability) params.set("recognizability", recognizability);
  if (language) params.set("language", language);
  const qs = params.toString();
  return request(`/mix${qs ? `?${qs}` : ""}`);
}

export function getPlaylists() {
  return request("/playlists");
}

export function createPlaylist(title) {
  return request("/playlist", { method: "POST", body: JSON.stringify({ title }) });
}

export function getPlaylistTracks(playlistId) {
  return request(`/playlists/${playlistId}/tracks`);
}

export function getAlbums() {
  return request("/albums");
}

export function getAlbumTracks(name) {
  return request(`/albums/tracks?name=${encodeURIComponent(name)}`);
}

// Исполнители с дедупликацией по нормализованному имени (ТЗ §13-14)
export function getArtists() {
  return request("/artists");
}

export function getArtistTracks(name) {
  return request(`/artists/tracks?name=${encodeURIComponent(name)}`);
}

// Жанры каталога (SPEC-КАТАЛОГ §1): дерево для чипов поиска + треки жанра
export function getGenres() {
  return request("/genres");
}

export function getGenreTracks(slug, page = 1, pageSize = 100) {
  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  return request(`/genres/${encodeURIComponent(slug)}/tracks?${params}`);
}

// Карточка артиста (SPEC-КАТАЛОГ §2): фото, баннер, жанры, топ, альбомы
export function getArtistCard(name) {
  return request(`/artist-card?name=${encodeURIComponent(name)}`);
}

// Реальные популярные запросы (ТЗ §11). Лог — только «закоммиченный» запрос.
export function getPopularQueries() {
  return request("/search/popular");
}

export function logSearchQuery(query) {
  return request("/search/log", { method: "POST", body: JSON.stringify({ query }) }).catch(() => {});
}

// «Скачать»: бот присылает аудиофайл в чат пользователя (ТЗ §9)
export function sendTrackToChat(trackId) {
  return request(`/tracks/${trackId}/send`, { method: "POST" });
}

// Отметить старт воспроизведения (сырьё для достижений). Fire-and-forget.
export function recordListen(trackId) {
  return request(`/tracks/${trackId}/listen`, { method: "POST" }).catch(() => {});
}

export function getLyrics(trackId) {
  return request(`/tracks/${trackId}/lyrics`);
}

export function submitLyrics(trackId, text) {
  return request(`/tracks/${trackId}/lyrics`, {
    method: "POST",
    body: JSON.stringify({ text }),
  });
}

// Загрузка своего трека файлом (multipart): исполнитель обязателен на сервере
export async function uploadTrack(file, title, artist) {
  const form = new FormData();
  form.append("title", title);
  form.append("artist", artist);
  form.append("file", file);
  // Без Content-Type вручную — браузер сам проставит boundary для multipart
  const response = await fetch(`${API_BASE}/upload`, {
    method: "POST",
    headers: { Authorization: `Bearer ${accessToken}` },
    body: form,
  });
  if (!response.ok) {
    const detail = await response
      .json()
      .then((body) => (typeof body.detail === "string" ? body.detail : ""))
      .catch(() => "");
    throw new ApiError(detail || `Ошибка загрузки (${response.status})`, response.status);
  }
  return response.json();
}

// Пробный Premium на 3 дня — один раз на аккаунт
export function startPremiumTrial() {
  return request("/premium/trial", { method: "POST" });
}

export function getReferralTop() {
  return request("/referral/top");
}

// Топ артистов и треков пользователя — блоки профиля
export function getProfileTop() {
  return request("/profile/top");
}

// Перенос плейлиста из другого сервиса: ссылка или список «Артист — Название»
export function startTransfer(source) {
  return request("/transfer", { method: "POST", body: JSON.stringify({ source }) });
}

export function createPaymentLink(months = 1) {
  return request("/premium/pay", { method: "POST", body: JSON.stringify({ months }) });
}

export function formatDuration(totalSeconds) {
  const seconds = Math.max(0, Math.round(totalSeconds || 0));
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

export function shuffle(list) {
  const result = [...list];
  for (let i = result.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    [result[i], result[j]] = [result[j], result[i]];
  }
  return result;
}

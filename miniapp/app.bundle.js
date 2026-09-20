// СОБРАНО АВТОМАТИЧЕСКИ — не править руками.

// Источник: miniapp/src/**. Пересборка: python tools/build_miniapp.py

// отпечаток исходников: 0e28b19cd363a01b

(function () {
  "use strict";
  const __m = {};

  __m["api.js"] = (function () {
    // Реальный API-клиент: JWT по Telegram WebApp initData, никаких моков.
    // В проде mini app и API живут на одном домене (nginx: /api → uvicorn).
    // В dev (порт 5500, python http.server) API поднимается отдельно на 8010.

    const IS_DEV = location.port === "5500";
    const API_BASE = IS_DEV ? "http://127.0.0.1:8010" : "/api";

    let accessToken = null;

    class ApiError extends Error {
      constructor(message, status) {
        super(message);
        this.status = status;
      }
    }

    function tg() {
      return window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
    }

    function telegramUser() {
      const webApp = tg();
      return webApp && webApp.initDataUnsafe ? webApp.initDataUnsafe.user || null : null;
    }

    async function login() {
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

    // Сколько ждём ответ сервера. Без предела зависшее соединение держало экран на
    // «Загружаю…» бесконечно (скрин владельца 19.09: «Плейлисты» на медленной сети).
    // 20 сек: сам сервер отвечает за десятки миллисекунд, столько ждём только сеть.
    const REQUEST_TIMEOUT_MS = 20000;

    async function request(path, options = {}) {
      // AbortController есть во всех живых браузерах; если его нет — работаем как раньше
      const control = typeof AbortController === "function" ? new AbortController() : null;
      const timer = control ? setTimeout(() => control.abort(), REQUEST_TIMEOUT_MS) : null;
      let response;
      try {
        response = await fetch(`${API_BASE}${path}`, {
          ...options,
          signal: control ? control.signal : undefined,
          headers: {
            Authorization: `Bearer ${accessToken}`,
            ...(options.body ? { "Content-Type": "application/json" } : {}),
            ...(options.headers || {}),
          },
        });
      } catch (error) {
        if (error && error.name === "AbortError") {
          throw new ApiError("Сеть не отвечает — попробуйте ещё раз", 0);
        }
        throw error;
      } finally {
        if (timer) clearTimeout(timer);
      }
      if (response.status === 401 && !options._retried) {
        // токен истёк — перелогин и РОВНО один повтор (иначе бесконечный цикл 401)
        await login();
        return request(path, { ...options, _retried: true });
      }
      if (response.status === 402) {
        // Пэйвол на сервере: Premium истёк посреди сессии — main.js покажет экран оплаты
        window.dispatchEvent(new CustomEvent("premium-required"));
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

    function resolveAudioUrl(track) {
      return track.audio_url ? `${API_BASE}${track.audio_url}` : null;
    }

    function getTracks(query = "", page = 1, pageSize = 100) {
      const params = new URLSearchParams({ q: query, page: String(page), page_size: String(pageSize) });
      return request(`/tracks?${params}`);
    }

    // Свежий трек по id (минус — отрицательный id): даёт новую подписанную audio_url,
    // когда кэшированная протухла (TTL 6 часов) или её нет вовсе (треки из «Недавних»).
    function getTrackById(trackId) {
      return request(`/track/${trackId}`);
    }

    // Минусы: приходят в формате треков с отрицательными id (вкладка «Минусы» в поиске)
    function getInstrumentals(query = "", page = 1, pageSize = 50) {
      const params = new URLSearchParams({ q: query, page: String(page), page_size: String(pageSize) });
      return request(`/instrumentals?${params}`);
    }

    function getLibrary(page = 1, pageSize = 100) {
      return request(`/library?page=${page}&page_size=${pageSize}`);
    }

    function getLibraryIds() {
      return request("/library/ids");
    }

    function addToLibrary(trackId) {
      return request(`/library/${trackId}`, { method: "POST" });
    }

    function removeFromLibrary(trackId) {
      return request(`/library/${trackId}`, { method: "DELETE" });
    }

    function getPremiumStatus() {
      return request("/premium/status");
    }

    // Статус обязательной подписки: required=false → гейт не показываем (нет каналов
    // или у пользователя Premium). force=true — перепроверить сразу, минуя кэш.
    function getSubscriptionStatus(force) {
      return request(`/subscription/status${force ? "?force=true" : ""}`);
    }

    // Клик по кнопке канала в гейте — воронка для продажи рекламы (fire-and-forget)
    function logChannelClick(channelId) {
      return request(`/subscription/click/${channelId}`, { method: "POST" });
    }

    // Нет в базе — ищем в открытых источниках; трек придёт в бота и в библиотеку
    function fetchFromWeb(query) {
      return request("/search/fetch", { method: "POST", body: JSON.stringify({ query }) });
    }

    // Живой поиск: выдача идёт прямо из источников, каталог для этого не нужен.
    function liveSearch(query) {
      return request(`/search/live?q=${encodeURIComponent(query)}`);
    }

    // Альбомы целиком (16.09): карточки под выдачей, треки альбома потоком,
    // «добавить весь альбом» — воркер импортирует треки в библиотеку.
    function searchLiveAlbums(query) {
      return request(`/search/live/albums?q=${encodeURIComponent(query)}`);
    }

    function getLiveAlbumTracks(albumId) {
      return request(`/albums/live/${albumId}`);
    }

    function addLiveAlbumToLibrary(albumId) {
      return request(`/albums/live/${albumId}/library`, { method: "POST" });
    }

    // Фоновая закачка выбранного трека: играет он уже потоком, а это — чтобы в
    // следующий раз играл мгновенно по file_id и остался в библиотеке.
    function queueLiveFetch(ref) {
      return request(`/search/live/${encodeURIComponent(ref)}/fetch`, { method: "POST" });
    }

    // Поток кандидата: <audio> идёт сюда, сервер проксирует источник с поддержкой Range
    function liveStreamUrl(ref) {
      return `/stream/${encodeURIComponent(ref)}`;
    }

    function getProfile() {
      return request("/profile");
    }

    // Активные конкурсы вместе с состоянием условий текущего пользователя
    function getContests() {
      return request("/contests");
    }

    // Участие: условия проверяет сервер, ответ приходит уже с обновлённым состоянием
    function joinContest(contestId) {
      return request(`/contests/${contestId}/join`, { method: "POST" });
    }

    function getMix({ mood, recognizability, language } = {}) {
      const params = new URLSearchParams();
      if (mood) params.set("mood", mood);
      if (recognizability) params.set("recognizability", recognizability);
      if (language) params.set("language", language);
      const qs = params.toString();
      return request(`/mix${qs ? `?${qs}` : ""}`);
    }

    function getPlaylists() {
      return request("/playlists");
    }

    function createPlaylist(title) {
      return request("/playlist", { method: "POST", body: JSON.stringify({ title }) });
    }

    function getPlaylistTracks(playlistId) {
      return request(`/playlists/${playlistId}/tracks`);
    }

    // Добавить трек в плейлист (референс: шит «Добавить в плейлист»)
    function addTrackToPlaylist(playlistId, trackId) {
      return request(`/playlists/${playlistId}/tracks/${trackId}`, { method: "POST" });
    }

    function getAlbums() {
      return request("/albums");
    }

    function getAlbumTracks(name) {
      return request(`/albums/tracks?name=${encodeURIComponent(name)}`);
    }

    // Исполнители с дедупликацией по нормализованному имени (ТЗ §13-14)
    function getArtists(limit) {
      return request(`/artists${limit ? `?limit=${limit}` : ""}`);
    }

    function getArtistTracks(name) {
      return request(`/artists/tracks?name=${encodeURIComponent(name)}`);
    }

    // Жанры каталога (SPEC-КАТАЛОГ §1): дерево для чипов поиска + треки жанра
    function getGenres() {
      return request("/genres");
    }

    function getGenreTracks(slug, page = 1, pageSize = 100) {
      const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
      return request(`/genres/${encodeURIComponent(slug)}/tracks?${params}`);
    }

    // Карточка артиста (SPEC-КАТАЛОГ §2): фото, баннер, жанры, топ, синглы, альбомы, похожие
    function getArtistCard(name) {
      return request(`/artist-card?name=${encodeURIComponent(name)}`);
    }

    // Подписка на артиста (референс: «Мои артисты», toggle в карточке)
    function followArtist(artistId) {
      return request(`/artists/${artistId}/follow`, { method: "POST" });
    }

    function unfollowArtist(artistId) {
      return request(`/artists/${artistId}/follow`, { method: "DELETE" });
    }

    function getMyArtists() {
      return request("/my/artists");
    }

    // Секционный поиск (референс): Артисты / Альбомы / Плейлисты / Треки
    function searchAll(query) {
      return request(`/search/all?q=${encodeURIComponent(query)}`);
    }

    // Реальные популярные запросы (ТЗ §11). Лог — только «закоммиченный» запрос.
    function getPopularQueries() {
      return request("/search/popular");
    }

    // results — сколько нашлось (null, если поиск упал): доля пустых поисков в аналитике
    function logSearchQuery(query, results = null) {
      return request("/search/log", { method: "POST", body: JSON.stringify({ query, results }) }).catch(() => {});
    }

    // Пачка событий аналитики (analytics.js копит и шлёт раз в несколько секунд)
    function sendAnalyticsEvents(events) {
      return request("/analytics/events", { method: "POST", body: JSON.stringify({ events }) });
    }

    // «Скачать»: бот присылает аудиофайл в чат пользователя (ТЗ §9)
    function sendTrackToChat(trackId) {
      return request(`/tracks/${trackId}/send`, { method: "POST" });
    }

    // Отметить старт воспроизведения (сырьё для достижений). Fire-and-forget.
    function recordListen(trackId) {
      return request(`/tracks/${trackId}/listen`, { method: "POST" }).catch(() => {});
    }

    function getLanguages() {
      return request("/languages");
    }

    // Язык интерфейса общий с ботом — хранится на сервере в users.ui_language
    function saveLanguage(code) {
      return request("/language", {
        method: "POST",
        body: JSON.stringify({ code }),
      });
    }

    function getLyrics(trackId) {
      return request(`/tracks/${trackId}/lyrics`);
    }

    function submitLyrics(trackId, text) {
      return request(`/tracks/${trackId}/lyrics`, {
        method: "POST",
        body: JSON.stringify({ text }),
      });
    }

    // Загрузка своего трека файлом (multipart): исполнитель обязателен на сервере
    async function uploadTrack(file, title, artist) {
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

    // Пробный Premium (TRIAL_DAYS на сервере) — один раз на аккаунт
    function startPremiumTrial() {
      return request("/premium/trial", { method: "POST" });
    }

    function getReferralTop() {
      return request("/referral/top");
    }

    // Топ артистов и треков пользователя — блоки профиля
    function getProfileTop() {
      return request("/profile/top");
    }

    // Перенос плейлиста из другого сервиса: ссылка или список «Артист — Название»
    function startTransfer(source) {
      return request("/transfer", { method: "POST", body: JSON.stringify({ source }) });
    }

    function createPaymentLink(months = 1) {
      return request("/premium/pay", { method: "POST", body: JSON.stringify({ months }) });
    }

    function formatDuration(totalSeconds) {
      const seconds = Math.max(0, Math.round(totalSeconds || 0));
      const m = Math.floor(seconds / 60);
      const s = seconds % 60;
      return `${m}:${String(s).padStart(2, "0")}`;
    }

    function shuffle(list) {
      const result = [...list];
      for (let i = result.length - 1; i > 0; i -= 1) {
        const j = Math.floor(Math.random() * (i + 1));
        [result[i], result[j]] = [result[j], result[i]];
      }
      return result;
    }
    return { API_BASE, ApiError, telegramUser, login, resolveAudioUrl, getTracks, getTrackById, getInstrumentals, getLibrary, getLibraryIds, addToLibrary, removeFromLibrary, getPremiumStatus, getSubscriptionStatus, logChannelClick, fetchFromWeb, liveSearch, searchLiveAlbums, getLiveAlbumTracks, addLiveAlbumToLibrary, queueLiveFetch, liveStreamUrl, getProfile, getContests, joinContest, getMix, getPlaylists, createPlaylist, getPlaylistTracks, addTrackToPlaylist, getAlbums, getAlbumTracks, getArtists, getArtistTracks, getGenres, getGenreTracks, getArtistCard, followArtist, unfollowArtist, getMyArtists, searchAll, getPopularQueries, logSearchQuery, sendAnalyticsEvents, sendTrackToChat, recordListen, getLanguages, saveLanguage, getLyrics, submitLyrics, uploadTrack, startPremiumTrial, getReferralTop, getProfileTop, startTransfer, createPaymentLink, formatDuration, shuffle };
  })();

  __m["analytics.js"] = (function () {
    const { sendAnalyticsEvents } = __m["api.js"];
    // События аналитики Mini App (15.09): дослушал / пропустил, экраны, пэйвол,
    // «поделиться». Копятся в очереди и уходят пачкой — не запросом на каждое:
    // раз в 8 секунд, при 50 штуках и при сворачивании приложения.
    // Прослушивание («listen») и скачивание пишет сервер сам — отсюда их не шлём.
    // Ошибка отправки ничего не ломает: аналитика — не повод мешать слушать музыку.

    const FLUSH_MS = 8000;
    const MAX_BATCH = 50;
    const MAX_QUEUE = 200;

    const queue = [];
    let timer = null;

    function trackClient(name, { trackId = null, props = null } = {}) {
      queue.push({ name, track_id: trackId, props });
      if (queue.length > MAX_QUEUE) queue.splice(0, queue.length - MAX_QUEUE);
      if (queue.length >= MAX_BATCH) {
        flushAnalytics();
      } else if (!timer) {
        timer = setTimeout(flushAnalytics, FLUSH_MS);
      }
    }

    function flushAnalytics() {
      clearTimeout(timer);
      timer = null;
      if (!queue.length) return;
      const batch = queue.splice(0, MAX_BATCH);
      try {
        Promise.resolve(sendAnalyticsEvents(batch)).catch(() => retry(batch));
      } catch {
        retry(batch);
      }
      if (queue.length) timer = setTimeout(flushAnalytics, FLUSH_MS);
    }

    // Пачка не ушла — возвращаем её в очередь и пробуем позже. Первая пачка уходит
    // раньше, чем приложение успело войти («открыл приложение» копится с загрузки),
    // и без возврата это событие терялось бы у каждого — проверено в браузере 16.09.
    function retry(batch) {
      queue.unshift(...batch);
      if (queue.length > MAX_QUEUE) queue.length = MAX_QUEUE;
      if (!timer) timer = setTimeout(flushAnalytics, FLUSH_MS);
    }

    if (typeof document !== "undefined") {
      document.addEventListener("visibilitychange", () => {
        if (document.visibilityState === "hidden") flushAnalytics();
      });
    }
    return { trackClient, flushAnalytics };
  })();

  __m["prefs.js"] = (function () {
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

    function getRecentTracks() {
      return readJson(RECENT_TRACKS_KEY, []);
    }

    function pushRecentTrack(track) {
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

    function getRecentSearches() {
      return readJson(RECENT_SEARCHES_KEY, []);
    }

    function pushRecentSearch(query) {
      const value = query.trim();
      if (!value) return;
      const rest = getRecentSearches().filter((q) => q.toLowerCase() !== value.toLowerCase());
      writeJson(RECENT_SEARCHES_KEY, [value, ...rest].slice(0, RECENT_SEARCHES_LIMIT));
    }

    function clearRecentSearches() {
      writeJson(RECENT_SEARCHES_KEY, []);
    }

    // ---------- Настройки рекомендаций ----------

    const DEFAULT_REC_SETTINGS = { mood: "", recognizability: "", language: "" };

    function getRecSettings() {
      return { ...DEFAULT_REC_SETTINGS, ...readJson(REC_SETTINGS_KEY, {}) };
    }

    function saveRecSettings(settings) {
      writeJson(REC_SETTINGS_KEY, { ...DEFAULT_REC_SETTINGS, ...settings });
    }

    function clearRecSettings() {
      writeJson(REC_SETTINGS_KEY, { ...DEFAULT_REC_SETTINGS });
    }

    function hasRecSettings() {
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

    function isOnboarded() {
      try {
        return localStorage.getItem(ONBOARDED_KEY) === "1";
      } catch {
        return true; // приватный режим — не мучаем онбордингом
      }
    }

    function setOnboarded() {
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
    function isOnboardedCloud() {
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

    function getUiSettings() {
      return { ...DEFAULT_UI_SETTINGS, ...readJson(UI_SETTINGS_KEY, {}) };
    }

    function saveUiSettings(settings) {
      writeJson(UI_SETTINGS_KEY, { ...DEFAULT_UI_SETTINGS, ...settings });
    }

    // Применить акцент к документу: [data-accent] переопределяет токены (tokens.css)
    function applyAccent(accent = getUiSettings().accent) {
      if (typeof document === "undefined") return;
      if (accent && accent !== "blue") {
        document.documentElement.dataset.accent = accent;
      } else {
        delete document.documentElement.dataset.accent;
      }
    }

    // ---------- Любимые исполнители (предпочтения) ----------

    function getFavoriteArtists() {
      return readJson(FAV_ARTISTS_KEY, []);
    }

    function isFavoriteArtist(artist) {
      return getFavoriteArtists().some((a) => a.toLowerCase() === artist.toLowerCase());
    }

    function toggleFavoriteArtist(artist) {
      const value = (artist || "").trim();
      if (!value) return;
      const current = getFavoriteArtists();
      const exists = current.some((a) => a.toLowerCase() === value.toLowerCase());
      const next = exists
        ? current.filter((a) => a.toLowerCase() !== value.toLowerCase())
        : [value, ...current];
      writeJson(FAV_ARTISTS_KEY, next);
    }
    return { getRecentTracks, pushRecentTrack, getRecentSearches, pushRecentSearch, clearRecentSearches, getRecSettings, saveRecSettings, clearRecSettings, hasRecSettings, isOnboarded, setOnboarded, isOnboardedCloud, getUiSettings, saveUiSettings, applyAccent, getFavoriteArtists, isFavoriteArtist, toggleFavoriteArtist };
  })();

  __m["offline.js"] = (function () {
    // Офлайн-кэш треков для Premium (доп. ТЗ, блок D). Это ЛОКАЛЬНОЕ кэширование
    // Mini App через Cache API (не скачивание файлов в память телефона): сохранённый
    // трек играет мгновенно и без повторной загрузки. Индекс сохранённых — в
    // localStorage; если Telegram очистит кэш, Cache API опустеет и трек надо сохранить
    // заново (индекс это переживёт, но воспроизведение упадёт на сеть).

    const CACHE_NAME = "tgmusic-offline-audio";
    const INDEX_KEY = "tgmusic-offline-tracks";

    function cacheKey(trackId) {
      return `/__offline_audio__/${trackId}`;
    }

    function readIndex() {
      try {
        return JSON.parse(localStorage.getItem(INDEX_KEY) || "[]");
      } catch {
        return [];
      }
    }

    function writeIndex(list) {
      try {
        localStorage.setItem(INDEX_KEY, JSON.stringify(list));
      } catch {
        // приватный режим / переполнение — молча
      }
    }

    const supported = typeof caches !== "undefined";

    function offlineSupported() {
      return supported;
    }

    function offlineTracks() {
      return readIndex();
    }

    function isOffline(trackId) {
      return readIndex().some((t) => t.id === trackId);
    }

    async function saveOffline(track, absoluteAudioUrl) {
      if (!supported) throw new Error("offline-unsupported");
      const cache = await caches.open(CACHE_NAME);
      const response = await fetch(absoluteAudioUrl);
      if (!response.ok) throw new Error("fetch-failed");
      await cache.put(cacheKey(track.id), response);
      const slim = {
        id: track.id,
        title: track.title,
        artist: track.artist,
        duration: track.duration,
        audio_url: track.audio_url,
      };
      writeIndex([slim, ...readIndex().filter((t) => t.id !== track.id)]);
    }

    async function removeOffline(trackId) {
      if (supported) {
        const cache = await caches.open(CACHE_NAME);
        await cache.delete(cacheKey(trackId));
      }
      writeIndex(readIndex().filter((t) => t.id !== trackId));
    }

    // Blob-URL закэшированного трека для мгновенного воспроизведения; null — нет в кэше.
    async function offlineBlobUrl(trackId) {
      if (!supported) return null;
      const cache = await caches.open(CACHE_NAME);
      const response = await cache.match(cacheKey(trackId));
      if (!response) return null;
      const blob = await response.blob();
      return URL.createObjectURL(blob);
    }
    return { offlineSupported, offlineTracks, isOffline, saveOffline, removeOffline, offlineBlobUrl };
  })();

  __m["state.js"] = (function () {
    const { resolveAudioUrl, shuffle, recordListen, getMix, getTrackById, getTracks } = __m["api.js"];
    const { pushRecentTrack, getRecSettings } = __m["prefs.js"];
    const { isOffline, offlineBlobUrl } = __m["offline.js"];
    const { trackClient } = __m["analytics.js"];
    // Трек переключается сам по окончании — это не пропуск (аналитика 15.09)
    let advancingOnEnd = false;

    function currentQueueTrack() {
      return state.queue && state.queueIndex >= 0 ? state.queue[state.queueIndex] : null;
    }

    // Плеер — настоящий <audio>: событие ended переключает следующий трек само,
    // без действий пользователя (ТЗ §3-4). Прогресс (timeupdate, ~4 раза/сек)
    // идёт по ОТДЕЛЬНОМУ каналу подписки: полный re-render на каждый тик — это
    // и есть источник лагов, структура DOM перерисовывается только на смену
    // экрана/трека/состояния.

    const state = {
      screen: "home",
      bootStatus: "loading", // loading | ready | error
      bootError: "",
      user: null, // из Telegram initData
      premium: null, // {active, until, price_rub}
      catalog: [], // подгруженный пул треков (для «Слушать всё» и главной)
      catalogTotal: 0,
      libraryIds: new Set(),
      libraryPageItems: [],
      libraryTotal: 0,
      searchResults: [],
      searchTotal: 0,
      searchQuery: "",
      searchStatus: "idle", // idle | loading | done
      liveResults: [], // выдача живого поиска: кандидаты из источников, ещё не треки базы
      liveAlbums: [], // альбомы живого поиска (16.09): карточки под выдачей треков
      queue: [],
      queueIndex: -1,
      currentTrack: null,
      isPlaying: false,
      shuffleMode: true,
      repeatMode: false, // повтор текущего трека (audio.loop)
      playerOpen: false,
      queueOpen: false, // панель «Очередь» в плеере (скрины VK доп копи/)
      playerSettingsOpen: false, // шит ⚙️: таймер сна + эквалайзер
      sleepMinutes: 0, // активный таймер сна (0 — выключен)
      sheetTrack: null,
      toast: "",
      recDraft: getRecSettings(), // редактируемый черновик настроек рекомендаций
      subDismissed: false, // карточка подписки скрыта на эту сессию
      docKey: "about", // активный статический документ (faq/privacy/license/about)
      profile: null, // геймификация: ранг, приглашённые, достижения (грузится при открытии профиля)
      referralTop: [], // топ приглашающих (лидерборд рефералки)
      contests: null, // активные конкурсы; null — ещё не загрузились, [] — конкурсов нет
      profileTop: null, // {artists, tracks} — топы пользователя в профиле
      profileStatus: "idle", // idle | loading | ready | error
      lyricsTrack: null, // трек, для которого открыт экран текста
      lyrics: null, // {text, source, found}
      lyricsStatus: "idle", // idle | loading | ready | error
      lyricsEditing: false,
      playlists: [],
      playlistsStatus: "idle",
      playlistCreating: false, // инлайн-форма «Создать плейлист»
      albums: [],
      albumsStatus: "idle",
      curators: [],
      curatorsStatus: "idle",
      searchMode: "tracks", // tracks | instrumentals — вкладки в поиске
      collectionTitle: "",
      collectionTracks: [],
      collectionLive: [], // живые треки альбома из источника — играют потоком по номеру
      collectionAlbumId: null, // id альбома источника: есть — показываем «Добавить весь альбом»
      collectionCover: null,
      collectionStatus: "idle",
      collectionType: "playlist", // playlist | album | artist — влияет на шапку экрана
      popularQueries: [], // реальные популярные запросы с сервера (ТЗ §11)
      genres: [], // дерево жанров с сервера — чипы в поиске (SPEC-КАТАЛОГ §1)
      artistCard: null, // карточка артиста: фото, баннер, жанры, топ, альбомы (§2)
      artistCardStatus: "idle", // idle | loading | ready | error
      myArtists: [], // подписки пользователя (референс «Мои артисты»)
      myArtistsStatus: "idle",
      playlistPickerTrack: null, // id трека для шита «Добавить в плейлист»
      searchSections: null, // секционная выдача поиска: {artists, albums, playlists, tracks}
      artists: [], // [{name, track_count}] с сервера, дедуп (ТЗ §13)
      artistsStatus: "idle",
      myTracksTab: "all", // all | downloaded (ТЗ §5)
      myTracksQuery: "",
      myTracksSort: "default", // default | newest | oldest | title | artist
      myTracksEdit: false,
      sortSheetOpen: false,
      myTracksMenuOpen: false, // шит «…» в шапке Моих треков (скачать всё / удалить скачанные)
      premiumMonths: 12, // выбранный тариф на экране Premium (ТЗ §24)
      transferService: "spotify", // экран «Перенос из других сервисов»
      transferSource: "",
      transferStatus: "idle", // idle | loading
      transferResult: "",
      upload: { file: null, fileName: "", title: "", artist: "", status: "idle", result: "" },
      onbActive: false, // онбординг при первом входе
      onbStep: 0,
      onbArtists: [], // исполнители для шага выбора
      subGate: null, // {required, subscribed, channels} — гейт обязательной подписки (блок B)
    };

    const structureListeners = new Set();
    const progressListeners = new Set();

    const audio = new Audio();
    audio.preload = "auto";
    // Для эквалайзера (Web Audio createMediaElementSource) источник должен быть
    // CORS-чистым; на same-origin прода атрибут безвреден
    audio.crossOrigin = "anonymous";

    function notify() {
      structureListeners.forEach((fn) => fn(state));
    }

    function subscribe(fn) {
      structureListeners.add(fn);
      return () => structureListeners.delete(fn);
    }

    function subscribeProgress(fn) {
      progressListeners.add(fn);
      return () => progressListeners.delete(fn);
    }

    audio.addEventListener("timeupdate", () => {
      progressListeners.forEach((fn) => fn(audio.currentTime, audio.duration || 0));
    });

    audio.addEventListener("ended", () => {
      const finished = currentQueueTrack();
      if (finished) trackClient("play_complete", { trackId: finished.id });
      advancingOnEnd = true;
      try {
        playNext();
      } finally {
        advancingOnEnd = false;
      }
    });

    audio.addEventListener("play", () => {
      if ("mediaSession" in navigator) navigator.mediaSession.playbackState = "playing";
      if (!state.isPlaying) {
        state.isPlaying = true;
        notify();
      }
    });

    audio.addEventListener("pause", () => {
      if ("mediaSession" in navigator && !audio.ended) navigator.mediaSession.playbackState = "paused";
      // pause в конце трека прилетает перед ended — не дёргаем структуру зря
      if (state.isPlaying && !audio.ended) {
        state.isPlaying = false;
        notify();
      }
    });

    // Возврат из фона: iOS/Android могли поставить аудио на паузу — восстанавливаем,
    // если пользователь не останавливал сам (state.isPlaying всё ещё true)
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible" && state.isPlaying && audio.paused) {
        audio.play().catch(() => {});
      }
    });

    let consecutiveErrors = 0;

    audio.addEventListener("error", () => {
      const track = state.currentTrack;
      if (!track) return;
      consecutiveErrors += 1;
      // Потолок 4, а не «длина очереди». Раньше при очереди в полсотни треков
      // человек видел полсотни сообщений «пропускаю» подряд — ровно то, на что
      // владелец пожаловался 15.08. Четырёх промахов достаточно, чтобы понять:
      // дело не в одном треке.
      //
      // Сервер в этот момент уже чинит: на мёртвый file_id API ставит трек в
      // очередь на переминт, и через минуту он играет. Об этом и говорим — иначе
      // «попробуйте позже» звучит как «сломалось навсегда».
      if (consecutiveErrors >= 4) {
        state.isPlaying = false;
        showToast("Восстанавливаем эти треки — попробуйте через минуту");
        notify();
        return;
      }
      // Ошибка чаще всего = протухшая подписанная ссылка (TTL 6 часов):
      // один раз перезапрашиваем свежую по id, скипаем только если и она не играет
      if (!track.audioRefreshed) {
        track.audioRefreshed = true;
        refreshAndPlay(track);
        return;
      }
      showToast("Не удалось загрузить трек — пропускаю");
      playNext();
    });

    audio.addEventListener("playing", () => {
      consecutiveErrors = 0;
      if (state.currentTrack) state.currentTrack.audioRefreshed = false; // заиграл — право на повторный рефреш вернулось
    });

    function getState() {
      return state;
    }

    function mutate(patch) {
      Object.assign(state, patch);
      notify();
    }

    // ---------- Навигация: стек экранов + позиции прокрутки (ТЗ §3-4) ----------
    // Возврат всегда ведёт туда, откуда открыли страницу, и на ту же позицию скролла.

    const navStack = [{ screen: "home", patch: {}, scroll: 0 }];

    function readScrollTop() {
      return typeof document !== "undefined" && document.scrollingElement
        ? document.scrollingElement.scrollTop
        : 0;
    }

    function applyScrollTop(value) {
      if (typeof document === "undefined" || !document.scrollingElement) return;
      document.scrollingElement.scrollTop = value;
      // второй проход после отрисовки — высота контента могла появиться позже
      requestAnimationFrame(() => {
        document.scrollingElement.scrollTop = value;
      });
    }

    function navigateTo(screen, patch = {}) {
      trackClient("screen_view", { props: { screen } });
      navStack[navStack.length - 1].scroll = readScrollTop();
      navStack.push({ screen, patch, scroll: 0 });
      Object.assign(state, patch);
      state.screen = screen;
      notify();
      applyScrollTop(0);
    }

    function goBack() {
      if (navStack.length <= 1) {
        resetToTab("home");
        return;
      }
      navStack.pop();
      const top = navStack[navStack.length - 1];
      Object.assign(state, top.patch);
      state.screen = top.screen;
      notify();
      applyScrollTop(top.scroll);
    }

    // Таб нижней навигации: стек сбрасывается — «Назад» внутри таба не скачет между табами
    function resetToTab(tab) {
      navStack.length = 1;
      navStack[0] = { screen: tab, patch: {}, scroll: 0 };
      state.screen = tab;
      notify();
      applyScrollTop(0);
    }

    let toastTimer = null;

    function showToast(text) {
      state.toast = text;
      notify();
      clearTimeout(toastTimer);
      toastTimer = setTimeout(() => {
        state.toast = "";
        notify();
      }, 2400);
    }

    function updateMediaSession(track) {
      if (!("mediaSession" in navigator)) return;
      const ms = navigator.mediaSession;
      ms.metadata = new MediaMetadata({
        title: track.title,
        artist: track.artist,
        artwork: track.cover_url
          ? [{ src: track.cover_url, sizes: "512x512", type: "image/jpeg" }]
          : [],
      });
      // Полный набор действий — управление с экрана блокировки и продолжение в фоне
      ms.setActionHandler("play", () => audio.play().catch(() => {}));
      ms.setActionHandler("pause", () => audio.pause());
      ms.setActionHandler("nexttrack", playNext);
      ms.setActionHandler("previoustrack", playPrev);
      try {
        ms.setActionHandler("seekto", (e) => {
          if (e.seekTime != null && audio.duration) audio.currentTime = e.seekTime;
        });
      } catch {
        // старый webview — перемотка с локскрина недоступна, не критично
      }
    }

    let currentObjectUrl = null;

    function playFrom(src, track) {
      if (state.currentTrack !== track) return; // трек сменился, пока резолвили источник
      audio.src = src;
      audio.play().catch(() => {
        // автоплей заблокирован до первого касания — ставим на паузу без паники
        state.isPlaying = false;
        notify();
      });
    }

    function revokeObjectUrl() {
      if (currentObjectUrl) {
        URL.revokeObjectURL(currentObjectUrl);
        currentObjectUrl = null;
      }
    }

    // Свежая подписанная ссылка по id: для треков из «Недавних» (audio_url не хранится)
    // и при ошибке воспроизведения (кэшированная ссылка старше 6 часов → 403).
    async function refreshAndPlay(track) {
      // Живой трек из источника (id «live:…») в базе не лежит: обновлять ссылку негде.
      // Раньше здесь уходил /track/live:… и получал 422 — лишний запрос перед тем же пропуском.
      if (typeof track.id === "string" && track.id.startsWith("live:")) {
        showToast("Не удалось загрузить трек — пропускаю");
        playNext();
        return;
      }
      try {
        const fresh = await getTrackById(track.id);
        if (state.currentTrack !== track) return; // трек сменился, пока ходили за ссылкой
        if (!fresh.audio_url) {
          showToast("У трека нет аудио");
          playNext();
          return;
        }
        track.audio_url = fresh.audio_url;
        playFrom(resolveAudioUrl(track), track);
      } catch {
        if (state.currentTrack !== track) return;
        showToast("Не удалось загрузить трек — пропускаю");
        playNext();
      }
    }

    function setAudioSource(track) {
      const playNetwork = () => {
        const url = resolveAudioUrl(track);
        if (!url) {
          refreshAndPlay(track); // трек из localStorage без ссылки — резолвим по id
          return;
        }
        playFrom(url, track);
      };

      if (isOffline(track.id)) {
        offlineBlobUrl(track.id).then((blobUrl) => {
          if (state.currentTrack !== track) {
            if (blobUrl) URL.revokeObjectURL(blobUrl);
            return;
          }
          revokeObjectUrl();
          if (blobUrl) {
            currentObjectUrl = blobUrl;
            playFrom(blobUrl, track);
          } else {
            playNetwork(); // кэш очищен Telegram — играем по сети
          }
        });
        return;
      }
      revokeObjectUrl();
      playNetwork();
    }

    // Прослушивание засчитываем, только если трек звучал хотя бы LISTEN_AFTER_MS.
    // Раньше запрос уходил на каждый старт: 60 быстрых «следующий» = 61 запрос, это
    // половина минутного лимита API (120) — и пролистанное считалось «прослушанным».
    const LISTEN_AFTER_MS = 5000;
    let listenTimer = null;

    function scheduleListen(track) {
      clearTimeout(listenTimer);
      if (typeof track.id !== "number" || track.id <= 0) return; // минусы и live:… не пишем
      listenTimer = setTimeout(() => {
        if (state.currentTrack === track && !audio.paused) recordListen(track.id);
      }, LISTEN_AFTER_MS);
    }

    function startTrack(index) {
      const track = state.queue[index];
      if (!track) return;
      state.queueIndex = index;
      state.currentTrack = track;
      state.isPlaying = true;
      audio.volume = 1; // страховка от «затихания»: держим полную громкость на каждом треке
      // live:… в «Недавних» не сыграет: ref живёт 6 часов, а id в базе у него нет
      if (typeof track.id === "number") pushRecentTrack(track);
      scheduleListen(track);
      setAudioSource(track);
      updateMediaSession(track);
      notify();
    }

    // Единая точка запуска очереди для всех разделов (Player Engine, ТЗ §7-8).
    function playTrack(track, contextList) {
      const source = contextList && contextList.length ? contextList : [track];
      if (state.shuffleMode) {
        state.queue = [track, ...shuffle(source.filter((t) => t.id !== track.id))];
        startTrack(0);
      } else {
        state.queue = source;
        startTrack(Math.max(0, source.findIndex((t) => t.id === track.id)));
      }
    }

    function playAll() {
      playMix(state.catalog, "В базе пока нет треков");
    }

    // Персональный микс под сохранённые настройки рекомендаций (настроение/тип/язык).
    async function playRecommended() {
      showToast("Собираю рекомендации…");
      try {
        const tracks = await getMix(getRecSettings());
        playMix(tracks, "Пока нечего рекомендовать");
      } catch {
        showToast("Не удалось собрать микс");
      }
    }

    // Mood-микс с карточки «Какой сейчас вайб?» на главной (тот же /mix, что «Настроить»).
    async function playVibe(mood) {
      showToast("Собираю подборку…");
      try {
        const tracks = await getMix({ mood });
        playMix(tracks, "Пока нет треков под это настроение");
      } catch {
        showToast("Не удалось собрать микс");
      }
    }

    // Запуск произвольного микса (варианты swipe-hero: вся база / любимые / рекомендации).
    function playMix(list, emptyMessage = "Здесь пока нет треков") {
      if (!list || !list.length) {
        showToast(emptyMessage);
        return;
      }
      state.queue = shuffle(list);
      startTrack(0);
      state.playerOpen = true;
      notify();
    }

    function togglePlay() {
      if (!state.currentTrack) return;
      if (audio.paused) {
        audio.play().catch(() => {});
      } else {
        audio.pause();
      }
    }

    function playNext() {
      if (!state.queue.length) return;
      if (!advancingOnEnd) {
        // Переключил сам раньше конца — пропуск; позиция в процентах говорит, «не зашло
        // с первых секунд» это или «дослушал почти до конца»
        const skipped = currentQueueTrack();
        if (skipped && audio.currentTime > 0) {
          const positionPct = audio.duration ? Math.round((audio.currentTime / audio.duration) * 100) : null;
          trackClient("play_skip", { trackId: skipped.id, props: { position_pct: positionPct } });
        }
      }
      let next = state.queueIndex + 1;
      if (next >= state.queue.length) {
        // очередь закончилась — новая случайная из того же пула (ТЗ §5)
        state.queue = shuffle(state.queue);
        next = 0;
      }
      startTrack(next);
    }

    function playPrev() {
      if (!state.queue.length) return;
      if (audio.currentTime > 3) {
        audio.currentTime = 0;
        return;
      }
      startTrack(Math.max(0, state.queueIndex - 1));
    }

    function seekToFraction(fraction) {
      if (!audio.duration) return;
      audio.currentTime = Math.min(audio.duration - 0.1, Math.max(0, fraction * audio.duration));
    }

    function toggleShuffle() {
      state.shuffleMode = !state.shuffleMode;
      notify();
    }

    function toggleRepeat() {
      state.repeatMode = !state.repeatMode;
      audio.loop = state.repeatMode; // loop=true — ended не стреляет, трек крутится сам
      notify();
    }

    // Прыжок на трек прямо из панели «Очередь» (скрины VK)
    function playQueueIndex(index) {
      if (index < 0 || index >= state.queue.length) return;
      startTrack(index);
    }

    // «Добавить в очередь» (референс): трек в конец очереди. Если очереди нет — играем сразу.
    function addToQueue(track) {
      if (!state.queue.length) {
        playTrack(track, [track]);
        showToast("Играет");
        return;
      }
      state.queue = [...state.queue, track];
      showToast("Добавлено в очередь");
      notify();
    }

    // «Воспроизвести следующим» (референс): трек сразу после текущего.
    function playNextInQueue(track) {
      if (!state.queue.length) {
        playTrack(track, [track]);
        return;
      }
      const rest = state.queue.slice(0, state.queueIndex + 1);
      const tail = state.queue.slice(state.queueIndex + 1);
      state.queue = [...rest, track, ...tail];
      showToast("Прозвучит следующим");
      notify();
    }

    // «Микс по треку»: очередь = сам трек + его исполнитель + общий микс
    async function playTrackMix(track) {
      showToast("Собираю микс по треку…");
      try {
        const [byArtist, mix] = await Promise.all([
          getTracks(track.artist || "", 1, 50),
          getMix({}),
        ]);
        const seen = new Set([track.id]);
        const pool = [...(byArtist.items || []), ...mix].filter(
          (t) => !seen.has(t.id) && seen.add(t.id)
        );
        state.queue = [track, ...shuffle(pool)];
        startTrack(0);
        state.playerOpen = true;
        state.sheetTrack = null;
        notify();
      } catch {
        showToast("Не удалось собрать микс");
      }
    }

    // Таймер сна: пауза через N минут (0 — выключить)
    let sleepTimerId = null;

    function setSleepTimer(minutes) {
      clearTimeout(sleepTimerId);
      sleepTimerId = null;
      state.sleepMinutes = minutes;
      if (minutes > 0) {
        sleepTimerId = setTimeout(() => {
          audio.pause();
          state.sleepMinutes = 0;
          showToast("Таймер сна: воспроизведение остановлено");
          notify();
        }, minutes * 60 * 1000);
        showToast(`Таймер сна: ${minutes} мин`);
      } else {
        showToast("Таймер сна выключен");
      }
      notify();
    }

    function openPlayer() {
      state.playerOpen = true;
      notify();
    }

    function closePlayer() {
      state.playerOpen = false;
      state.queueOpen = false;
      state.playerSettingsOpen = false;
      notify();
    }

    function openSheet(track) {
      state.sheetTrack = track;
      notify();
    }

    function closeSheet() {
      state.sheetTrack = null;
      notify();
    }
    return { audio, subscribe, subscribeProgress, getState, mutate, navigateTo, goBack, resetToTab, showToast, playTrack, playAll, playRecommended, playVibe, playMix, togglePlay, playNext, playPrev, seekToFraction, toggleShuffle, toggleRepeat, playQueueIndex, addToQueue, playNextInQueue, playTrackMix, setSleepTimer, openPlayer, closePlayer, openSheet, closeSheet };
  })();

  __m["components/icons.js"] = (function () {
    // Тонкие одноцветные line-иконки (stroke=currentColor) — без внешних шрифтов/CDN.
    const WRAP = (inner) =>
      `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${inner}</svg>`;

    const PATHS = {
      home: '<path d="M4 11.5 12 4l8 7.5"/><path d="M6 10v9a1 1 0 0 0 1 1h4v-6h2v6h4a1 1 0 0 0 1-1v-9"/>',
      search: '<circle cx="11" cy="11" r="6.5"/><path d="m20 20-4.3-4.3"/>',
      library: '<rect x="4" y="4" width="6" height="16" rx="1.5"/><rect x="14" y="8" width="6" height="12" rx="1.5"/>',
      settings:
        '<circle cx="12" cy="12" r="3"/><path d="M19.4 13.5a1.7 1.7 0 0 0 .34 1.87l.06.06a2.05 2.05 0 1 1-2.9 2.9l-.06-.06a1.7 1.7 0 0 0-1.87-.34 1.7 1.7 0 0 0-1 1.55V20a2.05 2.05 0 0 1-4.1 0v-.1a1.7 1.7 0 0 0-1.1-1.55 1.7 1.7 0 0 0-1.87.34l-.06.06a2.05 2.05 0 1 1-2.9-2.9l.06-.06a1.7 1.7 0 0 0 .34-1.87 1.7 1.7 0 0 0-1.55-1H4a2.05 2.05 0 0 1 0-4.1h.1a1.7 1.7 0 0 0 1.55-1.1 1.7 1.7 0 0 0-.34-1.87l-.06-.06a2.05 2.05 0 1 1 2.9-2.9l.06.06a1.7 1.7 0 0 0 1.87.34H10a1.7 1.7 0 0 0 1-1.55V4a2.05 2.05 0 0 1 4.1 0v.1a1.7 1.7 0 0 0 1 1.55 1.7 1.7 0 0 0 1.87-.34l.06-.06a2.05 2.05 0 1 1 2.9 2.9l-.06.06a1.7 1.7 0 0 0-.34 1.87V10c.14.45.55 1 1.55 1H20a2.05 2.05 0 0 1 0 4.1h-.1a1.7 1.7 0 0 0-1.5 1.4Z"/>',
      play: '<path d="M7 5.5v13l11-6.5-11-6.5Z" fill="currentColor" stroke="none"/>',
      pause: '<rect x="6.5" y="5" width="4" height="14" rx="1" fill="currentColor" stroke="none"/><rect x="13.5" y="5" width="4" height="14" rx="1" fill="currentColor" stroke="none"/>',
      prev: '<path d="M18 6 8 12l10 6V6Z" fill="currentColor" stroke="none"/><rect x="5" y="6" width="2" height="12" rx="1" fill="currentColor" stroke="none"/>',
      next: '<path d="M6 6l10 6L6 18V6Z" fill="currentColor" stroke="none"/><rect x="17" y="6" width="2" height="12" rx="1" fill="currentColor" stroke="none"/>',
      shuffle:
        '<path d="M3 6h3.5L15 17h6"/><path d="M17.5 6H21v3.5"/><path d="M3 17.5h3.5L11 12"/><path d="m7.5 8.5-2-2.5 2-2.5" transform="translate(0 0)"/><path d="M17.5 14 21 17.5 17.5 21"/><path d="M21 6l-3.5 3.5"/>',
      repeat: '<path d="M4 7h13a3 3 0 0 1 3 3v1"/><path d="m14 3 3 4-3 4"/><path d="M20 17H7a3 3 0 0 1-3-3v-1"/><path d="m10 21-3-4 3-4"/>',
      heart: '<path d="M12 20.2s-7.6-4.6-9.9-9.2C.6 7.3 2.7 4 6.2 4c2 0 3.5 1 4.9 2.6C12.4 5 13.9 4 15.9 4c3.5 0 5.6 3.3 4.1 7-2.3 4.6-9.9 9.2-9.9 9.2Z"/>',
      download: '<path d="M12 4v11"/><path d="m7.5 11 4.5 4.5L16.5 11"/><path d="M5 19.5h14"/>',
      clock: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
      playlist: '<path d="M4 6h13"/><path d="M4 12h13"/><path d="M4 18h8"/><circle cx="19" cy="17" r="2.4"/><path d="M21.4 17V8l-3 1"/>',
      plus: '<path d="M12 5v14"/><path d="M5 12h14"/>',
      check: '<path d="m5 12.5 4.5 4.5L19 7"/>',
      more: '<circle cx="5" cy="12" r="1.4" fill="currentColor" stroke="none"/><circle cx="12" cy="12" r="1.4" fill="currentColor" stroke="none"/><circle cx="19" cy="12" r="1.4" fill="currentColor" stroke="none"/>',
      share: '<circle cx="18" cy="5.5" r="2.3"/><circle cx="6" cy="12" r="2.3"/><circle cx="18" cy="18.5" r="2.3"/><path d="m8.1 10.8 7.8-4.2"/><path d="m8.1 13.2 7.8 4.2"/>',
      close: '<path d="m6 6 12 12"/><path d="M18 6 6 18"/>',
      chevron: '<path d="m9 6 6 6-6 6"/>',
      back: '<path d="m15 6-6 6 6 6"/>',
      "chevron-down": '<path d="m6 9 6 6 6-6"/>',
      note: '<circle cx="8" cy="17.5" r="2.6"/><path d="M10.6 17.5V5.8l7.4-1.6v10.2"/><circle cx="18" cy="15.4" r="2.6"/>',
      crown: '<path d="M4 8.5 8 12l4-6.5L16 12l4-3.5L18.5 18h-13Z"/><path d="M6.5 20h11"/>',
      bell: '<path d="M6.5 10a5.5 5.5 0 0 1 11 0c0 4 1.5 5.5 1.5 5.5h-14S6.5 14 6.5 10Z"/><path d="M10 19a2 2 0 0 0 4 0"/>',
      lock: '<rect x="5.5" y="10.5" width="13" height="9" rx="2"/><path d="M8.5 10.5V7.5a3.5 3.5 0 0 1 7 0v3"/>',
      doc: '<path d="M7 3.5h7l4 4V20a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4.5a1 1 0 0 1 1-1Z"/><path d="M14 3.5V8h4"/>',
      font: '<path d="M6 19 10.5 6h1.6L16.5 19"/><path d="M7.3 15h7"/><path d="M18 19v-6.5"/><path d="m16 14 2-1.8 2 1.8"/>',
      help: '<circle cx="12" cy="12" r="8.5"/><path d="M9.6 9.3a2.4 2.4 0 1 1 3.5 2.1c-.9.5-1.4 1-1.4 2"/><circle cx="12" cy="16.3" r="0.4" fill="currentColor" stroke="none"/>',
      theme: '<path d="M12 3.5a8.5 8.5 0 1 0 8.5 8.5A6.5 6.5 0 0 1 12 3.5Z"/>',
      logout: '<path d="M9 4H6a1.5 1.5 0 0 0-1.5 1.5v13A1.5 1.5 0 0 0 6 20h3"/><path d="M15.5 16.5 20 12l-4.5-4.5"/><path d="M20 12H9"/>',
      tune: '<path d="M5 8h9"/><path d="M18 8h1"/><circle cx="16" cy="8" r="2"/><path d="M5 16h1"/><path d="M10 16h9"/><circle cx="8" cy="16" r="2"/>',
      sparkles: '<path d="M12 4.5 13.6 9 18 10.5 13.6 12 12 16.5 10.4 12 6 10.5 10.4 9 12 4.5Z"/><path d="M18 15.5 18.8 18 21 18.8 18.8 19.6 18 22 17.2 19.6 15 18.8 17.2 18 18 15.5Z"/>',
      history: '<path d="M4 12a8 8 0 1 1 2.5 5.8"/><path d="M4 12H2m2 0 .2 2.6"/><path d="M12 8v4l3 2"/>',
      sun: '<circle cx="12" cy="12" r="4"/><path d="M12 3v2"/><path d="M12 19v2"/><path d="M4.9 4.9 6.3 6.3"/><path d="m17.7 17.7 1.4 1.4"/><path d="M3 12h2"/><path d="M19 12h2"/><path d="M4.9 19.1 6.3 17.7"/><path d="m17.7 6.3 1.4-1.4"/>',
      moon: '<path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5Z"/>',
      fire: '<path d="M12 3s5 3.5 5 8.5a5 5 0 0 1-10 0c0-2 1-3.5 1-3.5S9 10 10 10c0-2.5 2-4 2-7Z"/>',
      leaf: '<path d="M4 20c0-8 6-14 16-14 0 10-6 14-14 14a6 6 0 0 1-2 0Z"/><path d="M9 15c3-3 6-5 9-6"/>',
      album: '<circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="12" r="2.2"/>',
      mic: '<rect x="9" y="3.5" width="6" height="11" rx="3"/><path d="M6 11a6 6 0 0 0 12 0"/><path d="M12 17v3.5"/><path d="M9 20.5h6"/>',
      star: '<path d="M12 4l2.3 4.9 5.2.6-3.9 3.6 1 5.3-4.6-2.7-4.6 2.7 1-5.3-3.9-3.6 5.2-.6L12 4Z"/>',
      globe: '<circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17"/><path d="M12 3.5c2.5 2.4 3.8 5.4 3.8 8.5S14.5 18.1 12 20.5c-2.5-2.4-3.8-5.4-3.8-8.5S9.5 5.9 12 3.5Z"/>',
      lyrics: '<path d="M5 5h14"/><path d="M5 9h10"/><path d="M5 13h8"/><path d="M5 17h11"/>',
      "chevron-left": '<path d="m14.5 6-5.5 6 5.5 6"/>',
      import: '<path d="M12 3v11"/><path d="m8 10 4 4 4-4"/><path d="M4 17v2a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-2"/>',
      transfer: '<path d="M4 8h13l-3-3"/><path d="M20 16H7l3 3"/>',
      radio: '<circle cx="12" cy="12" r="2"/><path d="M8.5 8.5a5 5 0 0 0 0 7"/><path d="M15.5 8.5a5 5 0 0 1 0 7"/><path d="M5.6 5.6a9 9 0 0 0 0 12.8"/><path d="M18.4 5.6a9 9 0 0 1 0 12.8"/>',
      gear: '<circle cx="12" cy="12" r="3"/><path d="M12 2.8 13.6 5h2.7l.8 2.5 2.4 1.2-.5 2.7 1.7 2.1-1.7 2.1.5 2.7-2.4 1.2-.8 2.5h-2.7L12 21.2 10.4 19H7.7l-.8-2.5-2.4-1.2.5-2.7L3.3 10.5 5 8.4l-.5-2.7L6.9 4.5 7.7 2h2.7L12 2.8Z" transform="scale(0.92) translate(1,1)"/>',
      sound: '<path d="M5 9v6h3l5 4V5L8 9H5Z" fill="currentColor" stroke="none"/><path d="M16 9a4 4 0 0 1 0 6"/><path d="M18.5 6.5a8 8 0 0 1 0 11"/>',
      sliders: '<path d="M6 4v6"/><path d="M6 14v6"/><circle cx="6" cy="12" r="2"/><path d="M12 4v2"/><path d="M12 10v10"/><circle cx="12" cy="8" r="2"/><path d="M18 4v10"/><path d="M18 18v2"/><circle cx="18" cy="16" r="2"/>',
      palette: '<path d="M12 3a9 9 0 1 0 0 18h1.5a2 2 0 0 0 0-4H12a1.5 1.5 0 0 1 0-3h5.5A3.5 3.5 0 0 0 21 10.5 8 8 0 0 0 12 3Z"/><circle cx="7.5" cy="11" r="1" fill="currentColor" stroke="none"/><circle cx="10" cy="7.5" r="1" fill="currentColor" stroke="none"/><circle cx="14.5" cy="7" r="1" fill="currentColor" stroke="none"/>',
      database: '<ellipse cx="12" cy="6" rx="7" ry="2.6"/><path d="M5 6v12c0 1.4 3.1 2.6 7 2.6s7-1.2 7-2.6V6"/><path d="M5 12c0 1.4 3.1 2.6 7 2.6s7-1.2 7-2.6"/>',
      pencil: '<path d="M4 20h4L19.5 8.5a2.1 2.1 0 0 0-3-3L5 17v3Z"/><path d="m13.5 6.5 3 3"/>',
      trash: '<path d="M5 7h14"/><path d="M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/><path d="M7 7l1 12a1.5 1.5 0 0 0 1.5 1.5h5A1.5 1.5 0 0 0 16 19l1-12"/><path d="M10 11v6"/><path d="M14 11v6"/>',
      sort: '<path d="M7 4v13"/><path d="m4 14.5 3 3 3-3"/><path d="M17 20V7"/><path d="m14 9.5 3-3 3 3"/>',
      copy: '<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v1"/>',
      gift: '<rect x="4" y="9" width="16" height="4"/><path d="M6 13v7h12v-7"/><path d="M12 9v11"/><path d="M12 9C9 9 7 7.5 7 5.8 7 4.2 8.4 3.5 9.6 4.1 11 4.8 12 9 12 9Z"/><path d="M12 9c3 0 5-1.5 5-3.2 0-1.6-1.4-2.3-2.6-1.7C13 4.8 12 9 12 9Z"/>',
      headset: '<path d="M4 14v-2a8 8 0 0 1 16 0v2"/><rect x="3.5" y="13" width="4" height="6.5" rx="1.6"/><rect x="16.5" y="13" width="4" height="6.5" rx="1.6"/><path d="M20 18v1a2.5 2.5 0 0 1-2.5 2.5H13"/>',
    };

    function icon(name) {
      return WRAP(PATHS[name] || "");
    }
    return { icon };
  })();

  __m["components/cover.js"] = (function () {
    const { icon } = __m["components/icons.js"];
    // Обложка трека: настоящая картинка из источника (track.cover_url), а без неё —
    // детерминированная абстрактная заливка в палитре VK-минимализма по id.
    // Свой escape вместо импорта из trackRow — trackRow сам импортирует cover (цикл).

    function escapeAttr(value) {
      return String(value).replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
    }

    const VARIANTS = [
      { pos: "20% 25%", glow: "rgba(59,123,254,0.5)", base: "#1c1c1f", deep: "#2b3f7a" },
      { pos: "75% 20%", glow: "rgba(238,63,200,0.42)", base: "#1c1c1f", deep: "#5c2b63" },
      { pos: "30% 75%", glow: "rgba(123,70,232,0.45)", base: "#1c1c1f", deep: "#3a2f70" },
      { pos: "70% 70%", glow: "rgba(59,123,254,0.4)", base: "#1c1c1f", deep: "#24427d" },
      { pos: "50% 15%", glow: "rgba(238,63,200,0.36)", base: "#1c1c1f", deep: "#4a2a6b" },
      { pos: "25% 55%", glow: "rgba(123,70,232,0.42)", base: "#1c1c1f", deep: "#33306e" },
    ];

    function pick(track) {
      // Math.abs: у минусов id отрицательный, а -1 % 6 === -1 в JS → undefined.
      // У кандидатов живого поиска id строковый («live:<ref>») — там считаем по строке,
      // иначе Math.abs даёт NaN и заглушка падает вместо того, чтобы просто отрисоваться.
      const id = track.id;
      if (typeof id === "number" && Number.isFinite(id)) {
        return VARIANTS[Math.abs(id) % VARIANTS.length];
      }
      const text = String(id == null ? "" : id);
      let sum = 0;
      for (let i = 0; i < text.length; i += 1) sum += text.charCodeAt(i);
      return VARIANTS[sum % VARIANTS.length];
    }

    function coverStyle(track) {
      const v = pick(track);
      return [
        `radial-gradient(circle at ${v.pos}, ${v.glow}, transparent 55%)`,
        `linear-gradient(150deg, ${v.deep} 0%, ${v.base} 70%)`,
      ].join(", ");
    }

    // Размер обложки SoundCloud задаётся суффиксом имени файла (19.09, замер):
    // «-original» до 800 КБ — его грузили даже в строку списка на 46px; «-t500x500»
    // в плеере на экране ×3 выглядел мыльно, а «-t1080x1080» есть у всех (240 КБ).
    const SC_SIZE = /-(original|large|crop|small|badge|tiny|mini|t\d+x\d+)\.(jpe?g|png)(\?.*)?$/i;

    function sizedCover(url, big = false) {
      if (!url || !/sndcdn\.com\//.test(url) || !SC_SIZE.test(url)) return url;
      // Аватарки (обложка трека без своей картинки) крупнее 500 не бывают, а
      // «-t1080x1080» у них — растянутая мелочь того же качества
      const size = big && !/\/avatars-/.test(url) ? "t1080x1080" : big ? "t500x500" : "t300x300";
      return url.replace(SC_SIZE, `-${size}.$2`);
    }

    function hiResCover(url, className) {
      return sizedCover(url, className === "player-art");
    }

    // Обложка заполняет квадрат целиком (object-fit: cover) — решение владельца 19.09:
    // полосы по бокам и размытая подложка выглядели как рамка больше картинки.
    function renderCover(track, className = "track-cover") {
      if (track.cover_url) {
        const src = escapeAttr(hiResCover(track.cover_url, className));
        // При ошибке загрузки картинка убирается — остаётся градиентная заглушка
        return `
          <div class="${className} cover-art" style="background:${coverStyle(track)}">
            <img class="cover-img" src="${src}" alt="" loading="lazy" onerror="this.remove()" />
          </div>
        `;
      }
      return `
        <div class="${className} cover-art" style="background:${coverStyle(track)}">
          <span class="cover-facet"></span>
          <span class="cover-note-icon">${icon("note")}</span>
        </div>
      `;
    }
    return { coverStyle, sizedCover, renderCover };
  })();

  __m["components/trackRow.js"] = (function () {
    const { icon } = __m["components/icons.js"];
    const { renderCover } = __m["components/cover.js"];
    const { formatDuration } = __m["api.js"];
    // Один ряд трека — переиспользуется на Главной/Поиске/Библиотеке.
    // Минусы приходят с отрицательными id: у них нет библиотеки/шита — только воспроизведение.
    function renderTrackRow(track, { context, inLibrary = false, playing = false } = {}) {
      const isInstrumental = track.id < 0;
      const actions = isInstrumental
        ? ""
        : `
          <div class="track-actions">
            <button class="icon-btn${inLibrary ? " is-added" : ""}" data-action="toggle-library" data-id="${track.id}" aria-label="В библиотеку">
              ${icon(inLibrary ? "check" : "plus")}
            </button>
            <button class="icon-btn" data-action="open-sheet" data-id="${track.id}" aria-label="Ещё">${icon("more")}</button>
          </div>
        `;
      return `
        <div class="track-row${playing ? " is-playing" : ""}" data-action="play-track" data-id="${track.id}" data-context="${context}">
          ${renderCover(track)}
          <div class="track-info">
            <div class="track-title">${escapeHtml(track.title)}</div>
            <div class="track-artist">${escapeHtml(track.artist)} · ${formatDuration(track.duration)}</div>
          </div>
          ${actions}
        </div>
      `;
    }

    function renderTrackList(tracks, { context, state } = {}) {
      if (!tracks.length) return "";
      const currentId = state.currentTrack ? state.currentTrack.id : null;
      return tracks
        .map((t) =>
          renderTrackRow(t, {
            context,
            inLibrary: state.libraryIds.has(t.id),
            playing: t.id === currentId,
          })
        )
        .join("");
    }

    // Названия и имена приходят из источников (SoundCloud, YouTube) и от других
    // людей, то есть их пишет посторонний. Экранируем ВСЕ пять символов, включая
    // одинарную кавычку: без неё подстановка внутри url('…') в атрибуте style
    // (карточка артиста, баннер) позволяла выйти из скобок и подсунуть свой CSS.
    // Выйти из самого атрибута было нельзя — двойная кавычка закрывалась, — но
    // оставлять дыру в один символ незачем.
    function escapeHtml(text) {
      return String(text)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
    }
    return { renderTrackRow, renderTrackList, escapeHtml };
  })();

  __m["components/header.js"] = (function () {
    const { icon } = __m["components/icons.js"];
    const { escapeHtml } = __m["components/trackRow.js"];
    function initials(user) {
      if (!user) return "TG";
      const first = (user.first_name || "").trim();
      const last = (user.last_name || "").trim();
      const letters = `${first[0] || ""}${last[0] || ""}`.toUpperCase();
      return letters || (user.username || "TG").slice(0, 2).toUpperCase();
    }

    function renderHeader(state) {
      const premium = state.premium && state.premium.active;
      const user = state.user;
      const face = user && user.photo_url
        ? `<img class="avatar__img" src="${escapeHtml(user.photo_url)}" alt="" />`
        : escapeHtml(initials(user));
      // Бренд — Infinity Music (переименование 07.08); «TG MUSIC» здесь остался от старого имени
      return `
        <header class="header">
          <button class="icon-btn" data-action="open-settings" aria-label="Настройки">${icon("settings")}</button>
          <div class="brand"><span class="brand__tg">INFINITY</span><span class="brand__music">MUSIC</span></div>
          <button class="avatar${premium ? " avatar--premium" : ""}" data-action="open-profile" aria-label="Профиль">${face}</button>
        </header>
      `;
    }
    return { renderHeader };
  })();

  __m["components/bottomNav.js"] = (function () {
    const { icon } = __m["components/icons.js"];
    const ITEMS = [
      { id: "home", label: "Главная", icon: "home" },
      { id: "search", label: "Поиск", icon: "search" },
      { id: "library", label: "Библиотека", icon: "library" },
    ];

    function renderBottomNav(activeScreen) {
      const items = ITEMS.map((item) => {
        const active = item.id === activeScreen;
        return `
          <button class="nav-item${active ? " is-active" : ""}" data-action="nav" data-screen="${item.id}">
            ${icon(item.icon)}
            <span>${item.label}</span>
          </button>
        `;
      }).join("");

      return `
        <nav class="bottom-nav">
          <div class="bottom-nav__inner">${items}</div>
        </nav>
      `;
    }
    return { renderBottomNav };
  })();

  __m["components/miniPlayer.js"] = (function () {
    const { icon } = __m["components/icons.js"];
    const { renderCover } = __m["components/cover.js"];
    const { escapeHtml } = __m["components/trackRow.js"];
    function renderMiniPlayer(state) {
      const { currentTrack, isPlaying, playerOpen } = state;
      if (!currentTrack || playerOpen) return "";

      return `
        <div class="mini-player">
          <div class="mini-player__inner" data-action="open-player">
            ${renderCover(currentTrack, "mini-player__cover")}
            <div class="mini-player__info">
              <div class="mini-player__title">${escapeHtml(currentTrack.title)}</div>
              <div class="mini-player__artist">${escapeHtml(currentTrack.artist)}</div>
            </div>
            <button class="mini-player__play" data-action="toggle-play" data-stop="1" aria-label="Play/Pause">
              ${icon(isPlaying ? "pause" : "play")}
            </button>
            <div class="mini-player__progress"><div class="mini-player__progress-fill" id="mini-progress-fill"></div></div>
          </div>
        </div>
      `;
    }
    return { renderMiniPlayer };
  })();

  __m["components/playerScreen.js"] = (function () {
    const { icon } = __m["components/icons.js"];
    const { renderCover } = __m["components/cover.js"];
    const { escapeHtml } = __m["components/trackRow.js"];
    const { formatDuration } = __m["api.js"];
    const QUEUE_WINDOW = 120; // окно строк вокруг текущего трека — не рисуем тысячи узлов

    // Экран плеера по референсу VK Music (ТЗ §7): обложка, название с «+»/«…»,
    // ряд чипов Скачать/Текст, прогресс, контролы разумного размера.
    // Прогресс-узлы имеют id и обновляются напрямую из subscribeProgress —
    // компонент перерисовывается только при смене трека/состояния.
    function renderPlayerScreen(state) {
      const { currentTrack, isPlaying, shuffleMode } = state;
      if (!state.playerOpen || !currentTrack) return "";

      // Минус (id<0) и кандидат живого поиска (id "live:…", в базе его ещё нет):
      // библиотека, текст, скачивание и шит для них не работают. Раньше кнопки
      // рисовались с data-id="live:…" → Number() = NaN, и тапы молча ничего не делали.
      const isInstrumental = typeof currentTrack.id !== "number" || currentTrack.id < 0;
      const inLibrary = state.libraryIds.has(currentTrack.id);

      const metaActions = isInstrumental
        ? ""
        : `
          <div class="player-meta__actions">
            <button class="icon-btn${inLibrary ? " is-added" : ""}" data-action="toggle-library" data-id="${currentTrack.id}" aria-label="В библиотеку">${icon(inLibrary ? "check" : "plus")}</button>
            <button class="icon-btn" data-action="open-sheet" data-id="${currentTrack.id}" aria-label="Ещё">${icon("more")}</button>
          </div>
        `;

      const chips = isInstrumental
        ? ""
        : `
          <div class="player-chips h-scroll">
            <button class="player-chip" data-action="download" data-id="${currentTrack.id}">${icon("download")} Скачать</button>
            <button class="player-chip" data-action="play-track-mix" data-id="${currentTrack.id}">${icon("radio")} Микс по треку</button>
            <button class="player-chip" data-action="open-lyrics" data-id="${currentTrack.id}">${icon("lyrics")} Текст</button>
            <button class="player-chip player-chip--icon" data-action="open-player-settings" aria-label="Настройки">${icon("gear")}</button>
          </div>
        `;

      return `
        <div class="player-overlay">
          <div class="player-overlay__inner">
            <div class="player-topbar">
              <button class="icon-btn" data-action="close-player" aria-label="Свернуть">${icon("chevron-down")}</button>
              <span class="player-topbar__label">Сейчас играет</span>
              <span class="player-topbar__spacer"></span>
            </div>

            ${renderCover(currentTrack, "player-art")}

            <div class="player-meta">
              <div class="player-meta__text">
                <div class="player-meta__title">${escapeHtml(currentTrack.title)}</div>
                <div class="player-meta__artist">${escapeHtml(currentTrack.artist)}</div>
              </div>
              ${metaActions}
            </div>

            ${chips}

            <div class="player-progress">
              <div class="progress-track" data-action="seek">
                <div class="progress-track__fill" id="player-progress-fill" style="width:0%"></div>
                <div class="progress-track__thumb" id="player-progress-thumb" style="left:0%"></div>
              </div>
              <div class="progress-times">
                <span id="player-time-current">0:00</span>
                <span id="player-time-total">${formatDuration(currentTrack.duration)}</span>
              </div>
            </div>

            <div class="player-controls">
              <button class="player-controls__side${shuffleMode ? " is-active" : ""}" data-action="toggle-shuffle" aria-label="Случайный порядок">${icon("shuffle")}</button>
              <button class="player-controls__side" data-action="prev" aria-label="Предыдущий">${icon("prev")}</button>
              <button class="player-controls__play" data-action="toggle-play" aria-label="Play/Pause">${icon(isPlaying ? "pause" : "play")}</button>
              <button class="player-controls__side" data-action="next" aria-label="Следующий">${icon("next")}</button>
              <button class="player-controls__side${state.repeatMode ? " is-active" : ""}" data-action="toggle-repeat" aria-label="Повтор">${icon("repeat")}</button>
            </div>

            <div class="player-bottombar">
              <button class="player-bottombar__tab" data-action="open-queue">
                Очередь <span class="player-bottombar__count">${state.queue.length}</span>
              </button>
              ${isInstrumental ? "" : `<button class="player-bottombar__tab" data-action="open-lyrics" data-id="${currentTrack.id}">Текст</button>`}
            </div>
          </div>
          ${renderQueuePanel(state)}
          ${renderPlayerSettings(state)}
        </div>
      `;
    }

    // Панель «Очередь» (скрины VK): список очереди, текущий подсвечен, тап — играть
    function renderQueuePanel(state) {
      if (!state.queueOpen) return "";
      const start = Math.max(0, state.queueIndex - 10);
      const rows = state.queue
        .slice(start, start + QUEUE_WINDOW)
        .map((track, i) => {
          const index = start + i;
          const isCurrent = index === state.queueIndex;
          return `
            <button class="queue-row${isCurrent ? " is-current" : ""}" data-action="queue-jump" data-index="${index}">
              ${renderCover(track)}
              <div class="track-info">
                <div class="track-title">${escapeHtml(track.title)}</div>
                <div class="track-artist">${escapeHtml(track.artist)}</div>
              </div>
              ${isCurrent ? icon("sound") : ""}
            </button>
          `;
        })
        .join("");
      return `
        <div class="sheet-overlay" data-action="close-queue">
          <div class="sheet sheet--tall" data-action="noop">
            <div class="sheet__handle"></div>
            <div class="sheet__title">Очередь · ${state.queue.length}</div>
            <div class="queue-list">${rows}</div>
          </div>
        </div>
      `;
    }

    // Шит ⚙️ (скрины VK): таймер сна + эквалайзер
    function renderPlayerSettings(state) {
      if (!state.playerSettingsOpen) return "";
      const sleepOption = (minutes, label) => `
        <button class="sheet-item" data-action="sleep-set" data-min="${minutes}">
          <span style="flex:1;text-align:left">${label}</span>
          ${state.sleepMinutes === minutes && minutes > 0 ? icon("check") : ""}
        </button>
      `;
      return `
        <div class="sheet-overlay" data-action="close-player-settings">
          <div class="sheet" data-action="noop">
            <div class="sheet__handle"></div>
            <div class="sheet__title">Настройки</div>
            <button class="sheet-item" data-action="open-equalizer-from-player">
              ${icon("sliders")}<span style="flex:1;text-align:left">Эквалайзер</span>
            </button>
            <div class="sheet__title" style="margin-top:6px">Таймер сна</div>
            ${sleepOption(15, "15 минут")}
            ${sleepOption(30, "30 минут")}
            ${sleepOption(60, "60 минут")}
            ${state.sleepMinutes ? sleepOption(0, "Выключить таймер") : ""}
          </div>
        </div>
      `;
    }
    return { renderPlayerScreen };
  })();

  __m["components/trackSheet.js"] = (function () {
    const { icon } = __m["components/icons.js"];
    const { renderCover } = __m["components/cover.js"];
    const { escapeHtml } = __m["components/trackRow.js"];
    const { formatDuration } = __m["api.js"];
    const { isOffline, offlineSupported } = __m["offline.js"];
    function renderTrackSheet(state) {
      const track = state.sheetTrack;
      if (!track) return "";
      const inLibrary = state.libraryIds.has(track.id);
      const isPremium = state.premium && state.premium.active;
      const saved = isOffline(track.id);
      const offlineItem =
        isPremium && offlineSupported()
          ? `
            <button class="sheet-item" data-action="toggle-offline" data-id="${track.id}">
              ${icon(saved ? "check" : "download")} ${saved ? "Удалить из офлайна" : "Сохранить офлайн"}
            </button>
          `
          : "";

      return `
        <div class="sheet-overlay" data-action="close-sheet">
          <div class="sheet" data-action="noop">
            <div class="sheet__handle"></div>
            <div class="sheet__track">
              ${renderCover(track)}
              <div class="track-info">
                <div class="track-title">${escapeHtml(track.title)}</div>
                <div class="track-artist">${escapeHtml(track.artist)} · ${formatDuration(track.duration)}</div>
              </div>
            </div>
            <button class="sheet-item" data-action="toggle-library" data-id="${track.id}" data-from-sheet="1">
              ${icon(inLibrary ? "check" : "plus")}
              ${inLibrary ? "Убрать из библиотеки" : "Добавить в библиотеку"}
            </button>
            <button class="sheet-item" data-action="download" data-id="${track.id}">
              ${icon("download")} Скачать — бот пришлёт файл в чат
            </button>
            ${offlineItem}
            <button class="sheet-item" data-action="add-to-playlist" data-id="${track.id}">
              ${icon("playlist")} Добавить в плейлист
            </button>
            <button class="sheet-item" data-action="queue-add" data-id="${track.id}">
              ${icon("plus")} Добавить в очередь
            </button>
            <button class="sheet-item" data-action="queue-next" data-id="${track.id}">
              ${icon("next")} Воспроизвести следующим
            </button>
            <button class="sheet-item" data-action="play-track-mix" data-id="${track.id}">
              ${icon("radio")} Включить микс по треку
            </button>
            <button class="sheet-item" data-action="sheet-open-artist" data-artist="${escapeHtml(track.artist)}">
              ${icon("mic")} Перейти к артисту
            </button>
            <button class="sheet-item" data-action="open-lyrics" data-id="${track.id}">
              ${icon("lyrics")} Текст песни
            </button>
            <button class="sheet-item" data-action="share" data-id="${track.id}">
              ${icon("share")} Поделиться
            </button>
            <button class="sheet-item is-danger" data-action="close-sheet">
              ${icon("close")} Закрыть
            </button>
          </div>
        </div>
      `;
    }
    return { renderTrackSheet };
  })();

  __m["components/playlistPicker.js"] = (function () {
    const { icon } = __m["components/icons.js"];
    const { escapeHtml } = __m["components/trackRow.js"];
    // Шит «Добавить в плейлист» (референс): создать новый + список существующих.
    // state.playlistPickerTrack — id трека, который добавляем.

    function renderPlaylistPicker(state) {
      if (state.playlistPickerTrack == null) return "";
      const playlists = state.playlists || [];

      const list = playlists.length
        ? playlists
            .map(
              (p) => `
                <button class="sheet-item" data-action="picker-add" data-playlist="${p.id}">
                  ${icon("playlist")} ${escapeHtml(p.title)}
                  <span class="sheet-item__count">${p.track_count ?? ""}</span>
                </button>
              `
            )
            .join("")
        : '<div class="empty-state">У вас пока нет плейлистов</div>';

      return `
        <div class="sheet-overlay" data-action="close-playlist-picker">
          <div class="sheet" data-action="noop">
            <div class="sheet__handle"></div>
            <div class="sheet__title">Добавить в плейлист</div>
            <button class="sheet-item is-accent" data-action="picker-create">
              ${icon("plus")} Создать новый плейлист
            </button>
            ${list}
            <button class="sheet-item is-danger" data-action="close-playlist-picker">
              ${icon("close")} Закрыть
            </button>
          </div>
        </div>
      `;
    }
    return { renderPlaylistPicker };
  })();

  __m["screens/home.js"] = (function () {
    const { icon } = __m["components/icons.js"];
    const { getRecentTracks } = __m["prefs.js"];
    // Главная — копия главного экрана VK Музыки (скрины владельца в копи/):
    // полноэкранный hero «Слушать Infinity Mix» с сине-розовым волновым градиентом,
    // подсказка свайпа со стрелками (кликабельны — работает и мышью на ПК),
    // плитки быстрого доступа с иконкой слева, лента «Какой сейчас вайб?».
    // Списков треков на главной НЕТ (решение владельца — навсегда).

    function heroSlides(state) {
      return [
        {
          action: "play-recommended",
          mix: "",
          title: "Слушать Infinity Mix",
          subtitle: "Музыкальные рекомендации для вас",
          button: `<button class="hero-slide__setup" data-action="open-recommendations">${icon("tune")} Настроить</button>`,
          hint: "Проведите, чтобы включить свои треки",
        },
        {
          action: "play-mix",
          mix: "library",
          title: "Слушать мои треки",
          subtitle: state.libraryTotal
            ? "Любимые треки из вашей коллекции"
            : "Добавьте треки в библиотеку",
          button: "",
          hint: "Проведите, чтобы включить Infinity Mix",
        },
      ];
    }

    function renderHero(state) {
      const slides = heroSlides(state)
        .map(
          (slide) => `
            <div class="hero-slide" data-action="${slide.action}"${slide.mix ? ` data-mix="${slide.mix}"` : ""}>
              <div class="hero-slide__play">${icon("play")}</div>
              <div class="hero-slide__title">${slide.title}</div>
              <div class="hero-slide__subtitle">${slide.subtitle}</div>
              ${slide.button}
              <div class="hero-slide__hint">
                <button class="hero-arrow" data-action="hero-prev" aria-label="Предыдущий микс">${icon("chevron-left")}</button>
                <span>${slide.hint}</span>
                <button class="hero-arrow" data-action="hero-next" aria-label="Следующий микс">${icon("chevron")}</button>
              </div>
            </div>
          `
        )
        .join("");

      return `
        <div class="hero">
          <div class="hero__track h-scroll" data-role="hero-scroll">${slides}</div>
        </div>
      `;
    }

    function renderSubscription(state) {
      if (!state.premium || state.premium.active || state.subDismissed) return "";
      // Пока триал не использован — предлагаем его: бесплатное «попробовать»
      // конвертит кратно лучше, чем сразу ценник.
      const trial = state.profile && state.profile.trial_available;
      return `
        <div class="sub-card" data-action="${trial ? "start-trial" : "open-premium"}">
          <button class="sub-card__close" data-action="dismiss-sub" aria-label="Скрыть">${icon("close")}</button>
          <div class="sub-card__title">${trial ? `${state.premium.trial_days || 7} дней Premium бесплатно` : `Целый месяц — ${state.premium.price_rub} ₽`}</div>
          <div class="sub-card__subtitle">${trial ? "Без карты: офлайн, без рекламы, эквалайзер" : "Premium: без рекламы и офлайн"}</div>
          <span class="sub-card__cta">${trial ? "Забрать" : "Подключить"}</span>
        </div>
      `;
    }

    // Для тех, у кого Premium идёт (в том числе пробная неделя): напоминание, что его
    // можно продлить бесплатно — друзьями и достижениями (владелец 15.09: «чтобы
    // больше было взаимодействий»). Цифры — с сервера, из профиля.
    function renderEarnDays(state) {
      const profile = state.profile;
      if (!profile || !profile.referral) return "";
      const referral = profile.referral;
      const nearest = (profile.achievements || [])
        .filter((a) => !a.unlocked && a.reward_days > 0)
        .sort((a, b) => b.progress / b.target - a.progress / a.target || a.target - b.target)[0];
      const parts = [];
      if (referral.next_reward_days > 0 && referral.to_next_reward > 0) {
        parts.push(`+${referral.next_reward_days} дн. за друзей: ещё ${referral.to_next_reward}`);
      }
      if (nearest) {
        parts.push(`«${nearest.title}» ${nearest.progress}/${nearest.target} → +${nearest.reward_days} дн.`);
      }
      if (!parts.length) return "";
      return `
        <button class="ref-teaser" data-action="open-referral">
          <span class="ref-teaser__emoji">⏳</span>
          <span class="ref-teaser__text">
            <span class="ref-teaser__title">Продлите Premium бесплатно</span>
            <span class="ref-teaser__sub">${parts.join(" · ")}</span>
          </span>
          ${icon("chevron")}
        </button>
      `;
    }

    // Рефералка на главной: заметная точка входа для не-Premium (запрос владельца)
    function renderReferralTeaser(state) {
      if (!state.premium) return "";
      if (state.premium.active) return renderEarnDays(state);
      return `
        <button class="ref-teaser" data-action="open-referral">
          <span class="ref-teaser__emoji">🎁</span>
          <span class="ref-teaser__text">
            <span class="ref-teaser__title">Приглашай друзей — получай Premium</span>
            <span class="ref-teaser__sub">Награда приходит сразу, за первого же</span>
          </span>
          ${icon("chevron")}
        </button>
      `;
    }

    // Баннер конкурса — над плитками, чтобы розыгрыш видели все, кто открыл приложение
    function renderContestBanner(state) {
      const contest = (state.contests || [])[0];
      if (!contest) return "";
      return `
        <button class="contest-banner" data-action="open-contests">
          <span class="contest-banner__emoji">🎉</span>
          <span class="contest-banner__text">
            <span class="contest-banner__title">${contest.banner_text}</span>
            <span class="contest-banner__sub">
              ${contest.joined ? "Вы участвуете — ждём итогов" : "Нажмите, чтобы участвовать"}
            </span>
          </span>
          ${icon("chevron")}
        </button>
      `;
    }

    function renderTiles(state) {
      const recentCount = getRecentTracks().length;
      const tiles = [
        {
          action: "open-mytracks",
          ic: "library",
          tone: "magenta",
          title: "Мои треки",
          sub: state.libraryTotal ? `${state.libraryTotal} всего` : "Пока пусто",
        },
        {
          action: "open-recent",
          ic: "history",
          tone: "teal",
          title: "Недавнее",
          sub: recentCount ? "Вы слушали" : "",
        },
        {
          action: "open-playlists",
          ic: "playlist",
          tone: "violet",
          title: "Плейлисты",
          sub: "",
        },
      ];

      const items = tiles
        .map(
          (t) => `
            <button class="vk-tile" data-action="${t.action}">
              <span class="vk-tile__icon vk-tile__icon--${t.tone}">${icon(t.ic)}</span>
              <span class="vk-tile__text">
                <span class="vk-tile__title">${t.title}</span>
                ${t.sub ? `<span class="vk-tile__sub">${t.sub}</span>` : ""}
              </span>
            </button>
          `
        )
        .join("");

      return `<div class="vk-grid">${items}</div>`;
    }

    // Плейлисты по настроению — серверный микс /mix?mood= (тот же движок, что «Настроить»)
    const VIBES = [
      { mood: "love", label: "Любовь", tone: "love" },
      { mood: "happy", label: "Радостно", tone: "happy" },
      { mood: "sad", label: "Грустно", tone: "sad" },
      { mood: "energetic", label: "Активно", tone: "active" },
      { mood: "calm", label: "Спокойно", tone: "calm" },
    ];

    function renderVibes() {
      const cards = VIBES.map(
        (v) => `
          <button class="vibe-card vibe-card--${v.tone}" data-action="play-vibe" data-mood="${v.mood}">
            ${icon("play")}<span>${v.label}</span>
          </button>
        `
      ).join("");

      return `
        <div class="vibe-section">
          <div class="vibe-section__label">Выберите плейлист по настроению</div>
          <div class="vibe-section__title">Какой сейчас вайб?</div>
          <div class="vibe-row h-scroll">${cards}</div>
        </div>
      `;
    }

    function renderHome(state) {
      return `
        ${renderHero(state)}
        ${renderContestBanner(state)}
        ${renderSubscription(state)}
        ${renderTiles(state)}
        ${renderVibes()}
        ${renderReferralTeaser(state)}
      `;
    }
    return { renderHome };
  })();

  __m["screens/search.js"] = (function () {
    const { icon } = __m["components/icons.js"];
    const { renderTrackList, escapeHtml } = __m["components/trackRow.js"];
    const { renderCover, sizedCover } = __m["components/cover.js"];
    const { formatDuration } = __m["api.js"];
    const { getRecentSearches, getRecentTracks } = __m["prefs.js"];
    // Поиск (ТЗ §11 + скрины VK в копи/): сверху «История прослушивания» (недавние
    // треки), затем недавние запросы пользователя и реальные популярные запросы
    // (статистика сервера, без выдуманных списков).

    function chip(query) {
      return `
        <button class="search-chip" data-action="search-chip" data-q="${escapeHtml(query)}">
          ${icon("search")}<span>${escapeHtml(query)}</span>
        </button>
      `;
    }

    function renderSuggestions(state) {
      const recent = getRecentSearches();
      const popular = (state.popularQueries || []).filter(
        (q) => !recent.some((r) => r.toLowerCase() === q.toLowerCase())
      );

      const historyTracks = getRecentTracks().slice(0, 5);
      const historyBlock = historyTracks.length
        ? `
          <div class="section-head section-head--between">
            <span class="section-title">История прослушивания</span>
            <button class="link-more" data-action="open-recent">Все</button>
          </div>
          <div class="card">${renderTrackList(historyTracks, { context: "recent", state })}</div>
        `
        : "";

      const recentBlock = recent.length
        ? `
          <div class="section-head section-head--between">
            <span class="section-title">Недавние запросы</span>
            <button class="link-more" data-action="clear-recent-searches">Очистить</button>
          </div>
          <div class="chip-cloud">${recent.map(chip).join("")}</div>
        `
        : "";

      const popularBlock = popular.length
        ? `
          <div class="section-head"><span class="section-title">Популярные запросы</span></div>
          <div class="chip-cloud">${popular.map(chip).join("")}</div>
        `
        : "";

      // Жанры каталога (SPEC-КАТАЛОГ §1): топ-уровень дерева как чипы, тап → экран жанра
      const genres = state.genres || [];
      const genresBlock = genres.length
        ? `
          <div class="section-head"><span class="section-title">Жанры</span></div>
          <div class="chip-cloud">${genres
            .map(
              (g) => `
                <button class="search-chip" data-action="open-genre" data-slug="${escapeHtml(g.slug)}" data-name="${escapeHtml(g.name)}">
                  <span>${escapeHtml(g.name)}</span>
                </button>
              `
            )
            .join("")}</div>
        `
        : "";

      if (!historyBlock && !recentBlock && !popularBlock && !genresBlock) {
        return '<div class="empty-state">Введите название трека или исполнителя</div>';
      }
      return `${historyBlock}${recentBlock}${popularBlock}${genresBlock}`;
    }

    // Секционная выдача (референс): Артисты / Альбомы / Плейлисты / Треки.
    function renderSections(sections, state) {
      const blocks = [];

      if (sections.artists && sections.artists.length) {
        const cards = sections.artists
          .map((a) => {
            const avatar = a.photo_url
              ? `<img class="similar-artist__avatar" src="${escapeHtml(a.photo_url)}" alt="" loading="lazy" />`
              : `<span class="similar-artist__avatar similar-artist__avatar--letter">${escapeHtml((a.name[0] || "♪").toUpperCase())}</span>`;
            return `
              <button class="similar-artist" data-action="open-artist" data-artist="${escapeHtml(a.name)}">
                ${avatar}<span class="similar-artist__name">${escapeHtml(a.name)}</span>
              </button>
            `;
          })
          .join("");
        blocks.push(`
          <div class="section-head"><span class="section-title">Артисты</span></div>
          <div class="similar-artists">${cards}</div>
        `);
      }

      if (sections.albums && sections.albums.length) {
        const cards = sections.albums
          .map(
            (a) => `
              <button class="artist-album" data-action="open-album" data-name="${escapeHtml(a.name)}">
                ${
                  a.cover_url
                    ? `<img class="artist-album__cover" src="${escapeHtml(sizedCover(a.cover_url))}" alt="" loading="lazy" />`
                    : `<span class="artist-album__cover artist-album__cover--letter">${escapeHtml((a.name[0] || "♪").toUpperCase())}</span>`
                }
                <span class="artist-album__name">${escapeHtml(a.name)}</span>
                <span class="artist-album__count">${a.track_count} треков</span>
              </button>
            `
          )
          .join("");
        blocks.push(`
          <div class="section-head"><span class="section-title">Альбомы</span></div>
          <div class="artist-albums">${cards}</div>
        `);
      }

      if (sections.playlists && sections.playlists.length) {
        const rows = sections.playlists
          .map(
            (p) => `
              <button class="lib-row" data-action="open-playlist" data-id="${p.id}" data-title="${escapeHtml(p.title)}">
                ${icon("playlist")}
                <span class="lib-row__text"><span class="lib-row__title">${escapeHtml(p.title)}</span>
                <span class="lib-row__sub">${p.track_count} треков</span></span>
              </button>
            `
          )
          .join("");
        blocks.push(`
          <div class="section-head"><span class="section-title">Плейлисты</span></div>
          <div class="card">${rows}</div>
        `);
      }

      return blocks.join("");
    }

    // Треки в поиске приходят живьём из источников, а не из каталога: строку в базе
    // заводим только когда трек реально послушали. Поэтому у ряда нет id — есть ref,
    // и действия ограничены воспроизведением.
    function renderLiveRow(item, index, state) {
      const current = state.currentTrack;
      const playing = Boolean(current && current.live_ref === item.ref);
      return `
        <div class="track-row${playing ? " is-playing" : ""}" data-action="play-live" data-index="${index}">
          ${renderCover({ ...item, id: item.ref })}
          <div class="track-info">
            <div class="track-title">${escapeHtml(item.title)}</div>
            <div class="track-artist">${escapeHtml(item.artist)} · ${formatDuration(item.duration)}</div>
          </div>
        </div>
      `;
    }

    // Альбомы целиком из источника (16.09). Карточки — те же, что у альбомов
    // каталога, но открывают живой альбом: треки потоком, «добавить весь альбом».
    function renderLiveAlbums(state) {
      const albums = state.liveAlbums || [];
      if (!albums.length) return "";
      const cards = albums
        .map(
          (a, i) => `
            <button class="artist-album" data-action="open-live-album" data-index="${i}">
              ${
                a.cover_url
                  ? `<img class="artist-album__cover" src="${escapeHtml(sizedCover(a.cover_url))}" alt="" loading="lazy" />`
                  : `<span class="artist-album__cover artist-album__cover--letter">${escapeHtml((a.title[0] || "♪").toUpperCase())}</span>`
              }
              <span class="artist-album__name">${escapeHtml(a.title)}</span>
              <span class="artist-album__count">${escapeHtml(a.artist)} · ${a.track_count} тр.</span>
            </button>
          `
        )
        .join("");
      return `
        <div class="section-head"><span class="section-title">Альбомы</span></div>
        <div class="artist-albums">${cards}</div>
      `;
    }

    function renderLiveTracks(state) {
      const items = state.liveResults || [];
      if (!items.length) return "";
      return `
        <div class="section-head"><span class="section-title">Треки</span></div>
        <div class="card">${items.map((item, i) => renderLiveRow(item, i, state)).join("")}</div>
      `;
    }

    // Результаты живут в отдельном контейнере: ввод перерисовывает только его,
    // а не всё приложение (иначе инпут теряет фокус).
    function renderSearchResults(state) {
      const query = state.searchQuery.trim();
      if (!query) {
        return renderSuggestions(state);
      }
      if (state.searchStatus === "loading") {
        return '<div class="empty-state">Ищу…</div>';
      }

      // Минусы — плоский список; треки — секционная выдача
      if (state.searchMode === "instrumentals") {
        if (!state.searchResults.length) {
          return `<div class="empty-state">Ничего не найдено по «${escapeHtml(query)}»</div>`;
        }
        return `
          <div class="section-head"><span class="section-title">Найдено: ${state.searchTotal}</span></div>
          <div class="card">${renderTrackList(state.searchResults, { context: "search", state })}</div>
        `;
      }

      const sections = state.searchSections;
      const liveTracks = renderLiveTracks(state);
      const liveAlbums = renderLiveAlbums(state);
      const hasSections =
        sections && (sections.artists.length || sections.albums.length || sections.playlists.length);
      if (!liveTracks && !liveAlbums && !hasSections) {
        return `<div class="empty-state">Ничего не найдено по «${escapeHtml(query)}»
          <button class="btn btn--primary search-web-btn" data-action="search-web">Поискать ещё</button>
        </div>`;
      }
      return `${hasSections ? renderSections(sections, state) : ""}${liveAlbums}${liveTracks}`;
    }

    function renderSearch(state) {
      const isInstrumentals = state.searchMode === "instrumentals";
      return `
        <div class="pill-row search-mode">
          <button class="pill${isInstrumentals ? "" : " is-active"}" data-action="search-mode" data-mode="tracks">Треки</button>
          <button class="pill${isInstrumentals ? " is-active" : ""}" data-action="search-mode" data-mode="instrumentals">🎼 Минусы</button>
        </div>
        <div class="search-input">
          ${icon("search")}
          <input type="text" data-role="search-input" placeholder="Search" value="${escapeHtml(state.searchQuery)}" />
        </div>
        <div id="search-results">${renderSearchResults(state)}</div>
      `;
    }
    return { renderSearchResults, renderSearch };
  })();

  __m["screens/library.js"] = (function () {
    const { icon } = __m["components/icons.js"];
    // Библиотека: разделы-строки в стиле VK. «Онлайн-треки» удалены (ТЗ §15),
    // «Кураторы» заменены на «Исполнители» — куратор и есть исполнитель (ТЗ §14).

    function row(label, ic, action, sub = "") {
      return `
        <button class="pl-row" data-action="${action}">
          <span class="pl-cover pl-cover--icon">${icon(ic)}</span>
          <span class="pl-row__text">
            <span class="pl-row__title">${label}</span>
            ${sub ? `<span class="pl-row__sub">${sub}</span>` : ""}
          </span>
          ${icon("chevron")}
        </button>
      `;
    }

    function renderPremiumCard(state) {
      if (state.premium && state.premium.active) {
        return `
          <div class="premium-card">
            <div class="premium-card__icon">${icon("crown")}</div>
            <div>
              <div class="premium-card__title">Infinity Music Premium активен</div>
              <div class="premium-card__subtitle">Без рекламы и лимитов</div>
            </div>
          </div>
        `;
      }
      return `
        <div class="premium-card" data-action="open-premium">
          <div class="premium-card__icon">${icon("crown")}</div>
          <div>
            <div class="premium-card__title">Infinity Music Premium</div>
            <div class="premium-card__subtitle">от ${state.premium ? state.premium.price_rub : 21} ₽ в месяц</div>
          </div>
        </div>
      `;
    }

    function renderLibrary(state) {
      return `
        <div class="lib-mix-row">
          <button class="lib-mix-btn" data-action="play-mix" data-mix="library">
            <span class="lib-mix-btn__icon">${icon("shuffle")}</span>
            <span>Мой микс</span>
          </button>
          <button class="lib-mix-btn" data-action="play-recommended">
            <span class="lib-mix-btn__icon">${icon("sparkles")}</span>
            <span>Infinity Mix</span>
          </button>
        </div>

        ${row("Мои треки", "library", "open-mytracks", `${state.libraryTotal} треков`)}
        ${row("Недавно прослушанные", "history", "open-recent")}
        ${row("Плейлисты", "playlist", "open-playlists")}
        ${row("Альбомы", "album", "open-albums")}
        ${row("Мои артисты", "mic", "open-my-artists", "На кого подписаны")}
        ${row("Все исполнители", "mic", "open-artists")}

        <div class="lib-add-row">
          ${row("Загрузить трек", "import", "open-upload", "Свой файл — в библиотеку")}
          ${row("Перенести из сервисов", "transfer", "open-transfer", "Spotify · Яндекс · ВК")}
        </div>

        <div style="margin-top:16px">${renderPremiumCard(state)}</div>
      `;
    }
    return { renderLibrary };
  })();

  __m["screens/mytracks.js"] = (function () {
    const { icon } = __m["components/icons.js"];
    const { renderCover } = __m["components/cover.js"];
    const { escapeHtml } = __m["components/trackRow.js"];
    const { formatDuration } = __m["api.js"];
    const { offlineTracks } = __m["offline.js"];
    // «Мои треки» по референсу VK Music (ТЗ §5): вкладки Все/Скачанные, поиск,
    // Shuffle + Sort By, режим редактирования с удалением из библиотеки.

    const SORT_OPTIONS = [
      { id: "default", label: "По умолчанию" },
      { id: "newest", label: "Сначала новые" },
      { id: "oldest", label: "Сначала старые" },
      { id: "title", label: "По названию" },
      { id: "artist", label: "По исполнителю" },
    ];

    function myTracksList(state) {
      const source = state.myTracksTab === "downloaded" ? offlineTracks() : state.libraryPageItems;
      const query = state.myTracksQuery.trim().toLowerCase();
      let list = query
        ? source.filter(
            (t) =>
              (t.title || "").toLowerCase().includes(query) ||
              (t.artist || "").toLowerCase().includes(query)
          )
        : [...source];

      switch (state.myTracksSort) {
        case "newest":
          list.sort((a, b) => b.id - a.id);
          break;
        case "oldest":
          list.sort((a, b) => a.id - b.id);
          break;
        case "title":
          list.sort((a, b) => (a.title || "").localeCompare(b.title || "", "ru"));
          break;
        case "artist":
          list.sort((a, b) => (a.artist || "").localeCompare(b.artist || "", "ru"));
          break;
        default:
          break;
      }
      return list;
    }

    function trackRow(track, state) {
      const playing = state.currentTrack && state.currentTrack.id === track.id;
      const trailing = state.myTracksEdit
        ? `<button class="icon-btn mt-remove" data-action="mytracks-remove" data-id="${track.id}" aria-label="Удалить">${icon("trash")}</button>`
        : `
          <button class="icon-btn" data-action="download" data-id="${track.id}" aria-label="Скачать">${icon("download")}</button>
          <button class="icon-btn" data-action="open-sheet" data-id="${track.id}" aria-label="Ещё">${icon("more")}</button>
        `;
      return `
        <div class="track-row${playing ? " is-playing" : ""}" data-action="play-track" data-id="${track.id}" data-context="mytracks">
          ${renderCover(track)}
          <div class="track-info">
            <div class="track-title">${escapeHtml(track.title)}</div>
            <div class="track-artist">${escapeHtml(track.artist)} · ${formatDuration(track.duration)}</div>
          </div>
          <div class="track-actions">${trailing}</div>
        </div>
      `;
    }

    function renderSortSheet(state) {
      if (!state.sortSheetOpen) return "";
      const rows = SORT_OPTIONS.map(
        (o) => `
          <button class="sheet-item" data-action="mytracks-sort" data-value="${o.id}">
            <span style="flex:1;text-align:left">${o.label}</span>
            ${state.myTracksSort === o.id ? icon("check") : ""}
          </button>
        `
      ).join("");
      return `
        <div class="sheet-overlay" data-action="close-sort-sheet">
          <div class="sheet" data-action="noop">
            <div class="sheet__handle"></div>
            <div class="sheet__title">Сортировка</div>
            ${rows}
          </div>
        </div>
      `;
    }

    // Шит «…» в шапке — как в VK (копи/ photo_1): скачать всё / редактировать / удалить скачанные
    function renderMenuSheet(state) {
      if (!state.myTracksMenuOpen) return "";
      const downloaded = offlineTracks().length;
      return `
        <div class="sheet-overlay" data-action="close-mytracks-menu">
          <div class="sheet" data-action="noop">
            <div class="sheet__handle"></div>
            <button class="sheet-item" data-action="mytracks-download-all">
              ${icon("download")}<span style="flex:1;text-align:left">Скачать всё</span>
            </button>
            <button class="sheet-item" data-action="mytracks-edit-from-menu">
              ${icon("pencil")}<span style="flex:1;text-align:left">Редактировать мои треки</span>
            </button>
            <button class="sheet-item${downloaded ? "" : " is-disabled"}" data-action="clear-offline" style="color:#e35d6a">
              ${icon("trash")}<span style="flex:1;text-align:left">Удалить скачанные треки</span>
            </button>
            <button class="sheet-item" data-action="close-mytracks-menu">
              <span style="flex:1;text-align:center;font-weight:700">Закрыть</span>
            </button>
          </div>
        </div>
      `;
    }

    function renderMyTracks(state) {
      const list = myTracksList(state);
      const isDownloads = state.myTracksTab === "downloaded";
      const sortLabel = (SORT_OPTIONS.find((o) => o.id === state.myTracksSort) || SORT_OPTIONS[0]).label;

      const head = `
        <div class="page-head" data-role="page-head">
          <button class="icon-btn" data-action="back" aria-label="Назад">${icon("back")}</button>
          <span>Мои треки</span>
          <span style="display:flex;gap:6px">
            <button class="icon-btn page-head__action${state.myTracksEdit ? " is-active" : ""}" data-action="mytracks-edit" aria-label="Редактировать">${icon("pencil")}</button>
            <button class="icon-btn page-head__action" data-action="open-mytracks-menu" aria-label="Ещё">${icon("more")}</button>
          </span>
        </div>
      `;

      const tabs = `
        <div class="seg-row">
          <button class="seg${isDownloads ? "" : " is-active"}" data-action="mytracks-tab" data-tab="all">
            Все <span class="seg__count">${state.libraryTotal}</span>
          </button>
          <button class="seg${isDownloads ? " is-active" : ""}" data-action="mytracks-tab" data-tab="downloaded">
            Скачанные <span class="seg__count">${offlineTracks().length}</span>
          </button>
        </div>
      `;

      const searchBox = `
        <div class="search-input search-input--compact">
          ${icon("search")}
          <input type="text" data-role="mytracks-search" placeholder="Search" value="${escapeHtml(state.myTracksQuery)}" />
        </div>
      `;

      const toolbar = `
        <div class="mt-toolbar">
          <button class="mt-shuffle" data-action="mytracks-shuffle">${icon("shuffle")}<span>Перемешать</span></button>
          <button class="mt-sort" data-action="open-sort-sheet">${sortLabel} ${icon("chevron-down")}</button>
        </div>
      `;

      return `${head}${tabs}${searchBox}${toolbar}<div id="mytracks-body">${renderMyTracksBody(state)}</div>${renderSortSheet(state)}${renderMenuSheet(state)}`;
    }

    // Тело списка — отдельно: ввод в поиске перерисовывает только его (фокус не теряется)
    function renderMyTracksBody(state) {
      const list = myTracksList(state);
      const isDownloads = state.myTracksTab === "downloaded";
      if (!list.length) {
        return isDownloads
          ? '<div class="empty-state">Нет скачанных треков.<br />«Ещё» у трека → «Сохранить офлайн» (Premium).</div>'
          : state.myTracksQuery.trim()
            ? `<div class="empty-state">Ничего не найдено по «${escapeHtml(state.myTracksQuery.trim())}»</div>`
            : '<div class="empty-state">Библиотека пуста.<br />Добавляйте треки кнопкой «+» из поиска.</div>';
      }
      const more =
        !isDownloads && !state.myTracksQuery.trim() && state.libraryPageItems.length < state.libraryTotal
          ? '<button class="btn btn--ghost btn--block" style="margin-top:12px" data-action="library-more">Показать ещё</button>'
          : "";
      return `<div class="card home-track-card">${list.map((t) => trackRow(t, state)).join("")}</div>${more}`;
    }
    return { SORT_OPTIONS, myTracksList, renderMyTracks, renderMyTracksBody };
  })();

  __m["screens/profile.js"] = (function () {
    const { icon } = __m["components/icons.js"];
    const { escapeHtml } = __m["components/trackRow.js"];
    // Профиль (ТЗ §22): аватар из Telegram, без блока «Друзья» и огромной кнопки —
    // рефералка живёт в своём разделе (§23), Premium — на экране тарифов (§24).

    function initials(user) {
      if (!user) return "TG";
      return `${(user.first_name || "")[0] || ""}${(user.last_name || "")[0] || ""}`.toUpperCase() || "TG";
    }

    function avatar(user, isPremium) {
      const cls = `avatar avatar--lg${isPremium ? " avatar--premium" : ""}`;
      if (user && user.photo_url) {
        return `<span class="${cls}"><img class="avatar__img" src="${escapeHtml(user.photo_url)}" alt="" /></span>`;
      }
      return `<span class="${cls}">${initials(user)}</span>`;
    }

    function formatUntil(iso) {
      return new Date(iso).toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit", year: "numeric" });
    }

    function statTile(value, label) {
      return `
        <div class="pstat">
          <div class="pstat__value">${value}</div>
          <div class="pstat__label">${label}</div>
        </div>
      `;
    }

    function achievementPreview(profile) {
      const shown = profile.achievements.slice(0, 8);
      const badges = shown
        .map(
          (a) => `<span class="ach-badge${a.unlocked ? " is-unlocked" : ""}" title="${escapeHtml(a.title)}">${a.emoji}</span>`
        )
        .join("");
      return `
        <div class="section-head">
          <span class="section-title">Достижения · ${profile.achievements_unlocked}/${profile.achievements_total}</span>
          <button class="link-more" data-action="open-achievements">Все ${icon("chevron")}</button>
        </div>
        <div class="ach-preview">${badges}</div>
      `;
    }

    function renderProfile(state) {
      const user = state.user;
      const name = user
        ? `${user.first_name || ""} ${user.last_name || ""}`.trim() || user.username || "Слушатель"
        : "Слушатель";
      const profile = state.profile;
      const isPremium = profile ? profile.premium.active : state.premium && state.premium.active;
      const rank = profile && profile.referral.rank ? profile.referral.rank : null;

      const head = `
        <div class="page-head" data-role="page-head">
          <button class="icon-btn" data-action="back" aria-label="Назад">${icon("back")}</button>
          <span>Профиль</span>
        </div>
      `;

      // Шапка по скринам VK (копи/ photo_28): цветной градиент во всю ширину,
      // круглый аватар по центру, имя и любимые жанры-теги под ним.
      const tags = (state.profileTop && state.profileTop.artists.length
        ? state.profileTop.artists.slice(0, 4).map((a) => a.name)
        : []
      )
        .map((t) => escapeHtml(t))
        .join(" · ");

      const hero = `
        <div class="profile-hero profile-hero--wide">
          ${avatar(user, isPremium)}
          <div class="profile-hero__name">
            ${escapeHtml(name)}${rank ? ` <span class="rank-badge">${rank.emoji} ${rank.title}</span>` : ""}
          </div>
          ${tags ? `<div class="profile-hero__tags">${tags}</div>` : ""}
          <div class="profile-hero__status${isPremium ? " is-premium" : ""}">
            ${
              isPremium && profile && profile.premium.until
                ? `Premium до ${formatUntil(profile.premium.until)}`
                : isPremium
                  ? "Premium активен"
                  : "Бесплатный тариф"
            }
          </div>
        </div>
      `;

      if (state.profileStatus === "loading" && !profile) {
        return `${head}${hero}<div class="empty-state">Загружаю профиль…</div>`;
      }

      const premiumCard = isPremium
        ? `
          <div class="premium-card">
            <div class="premium-card__icon">${icon("crown")}</div>
            <div>
              <div class="premium-card__title">Infinity Music Premium активен</div>
              <div class="premium-card__subtitle">Без рекламы и лимитов</div>
            </div>
          </div>
        `
        : `
          <div class="premium-card" data-action="open-premium">
            <div class="premium-card__icon">${icon("crown")}</div>
            <div>
              <div class="premium-card__title">Infinity Music Premium</div>
              <div class="premium-card__subtitle">от ${state.premium ? state.premium.price_rub : 21} ₽ в месяц</div>
            </div>
          </div>
        `;

      const referralRow = `
        <button class="settings-row" data-action="open-referral" style="width:100%;margin-top:10px">
          <div class="settings-row__label">${icon("gift")}Реферальная программа</div>
          ${icon("chevron")}
        </button>
      `;

      if (!profile) {
        return `${head}${hero}${premiumCard}${referralRow}`;
      }

      return `
        ${head}${hero}

        <div class="pstat-grid pstat-grid--3">
          ${statTile(profile.achievements_unlocked, "Достижений")}
          ${statTile(profile.stats.listens, "Прослушано")}
          ${statTile(profile.stats.streak_days, "Дней подряд")}
        </div>

        ${premiumCard}
        ${referralRow}
        ${topArtists(state)}
        ${topTracks(state)}
        ${achievementPreview(profile)}
      `;
    }

    // «Топ артистов» и «Топ треков» — нумерованные списки как на скринах VK
    function topArtists(state) {
      const artists = state.profileTop ? state.profileTop.artists : [];
      if (!artists.length) return "";
      const rows = artists
        .map(
          (artist, i) => `
            <button class="top-row" data-action="open-artist" data-artist="${escapeHtml(artist.name)}">
              <span class="top-row__num">${i + 1}</span>
              <span class="top-row__name">${escapeHtml(artist.name)}</span>
              <span class="top-row__count">${artist.track_count}</span>
            </button>
          `
        )
        .join("");
      return `
        <div class="section-head"><span class="section-title">Топ артистов</span></div>
        <div class="card card--flat top-list">${rows}</div>
      `;
    }

    function topTracks(state) {
      const tracks = state.profileTop ? state.profileTop.tracks : [];
      if (!tracks.length) return "";
      const rows = tracks
        .map(
          (track, i) => `
            <button class="top-row" data-action="play-track" data-id="${track.id}" data-context="profile-top">
              <span class="top-row__num">${i + 1}</span>
              <span class="top-row__name">
                ${escapeHtml(track.title)}
                <span class="top-row__artist">${escapeHtml(track.artist)}</span>
              </span>
            </button>
          `
        )
        .join("");
      return `
        <div class="section-head"><span class="section-title">Топ треков</span></div>
        <div class="card card--flat top-list">${rows}</div>
      `;
    }
    return { renderProfile };
  })();

  __m["i18n.js"] = (function () {
    // Мультиязычность Mini App — заготовка, зеркало app/i18n.py.
    //
    // Переведены русский и английский. Остальные языки уже выбираются, но пока
    // показывают английский: чтобы включить язык, достаточно наполнить его словарь.
    // Цепочка: выбранный язык → английский → русский → сам ключ.
    //
    // Выбор хранится на сервере (users.ui_language), поэтому бот и приложение
    // всегда говорят с человеком на одном языке.

    const DEFAULT_LANGUAGE = "ru";
    const FALLBACK_LANGUAGE = "en";

    const LANGUAGES = [
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

    function normalizeLanguage(code) {
      if (!code) return DEFAULT_LANGUAGE;
      const base = String(code).split("-")[0].toLowerCase();
      if (SUPPORTED.has(base)) return base;
      return RUSSIAN_NEIGHBOURS.has(base) ? DEFAULT_LANGUAGE : FALLBACK_LANGUAGE;
    }

    function isTranslated(code) {
      return Object.keys(TRANSLATIONS[code] || {}).length > 0;
    }

    function setLanguage(code) {
      current = normalizeLanguage(code);
      document.documentElement.lang = current;
      return current;
    }

    function getLanguage() {
      return current;
    }

    function t(key, vars) {
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
    return { DEFAULT_LANGUAGE, FALLBACK_LANGUAGE, LANGUAGES, normalizeLanguage, isTranslated, setLanguage, getLanguage, t };
  })();

  __m["screens/settings.js"] = (function () {
    const { icon } = __m["components/icons.js"];
    const { t } = __m["i18n.js"];
    // Настройки по референсу VK Music (ТЗ §16, §21): секции строк, «Поддержка
    // Telegram» вместо «Написать боту», версия — внутри «О приложении».

    function navRow(label, ic, action, data = "") {
      return `
        <button class="settings-row" data-action="${action}"${data} style="width:100%">
          <div class="settings-row__label">${icon(ic)}${label}</div>
          ${icon("chevron")}
        </button>
      `;
    }

    function renderSettings(state) {
      return `
        <div class="page-head" data-role="page-head">
          <button class="icon-btn" data-action="back" aria-label="Назад">${icon("back")}</button>
          <span>Настройки</span>
        </div>

        <div class="rec-section-label">Музыка</div>
        <div class="card card--rows">
          ${navRow("Настройки Infinity Mix", "tune", "open-recommendations")}
          ${navRow("Любимые исполнители", "mic", "open-artists")}
          ${navRow("Эквалайзер", "sliders", "open-equalizer")}
        </div>

        <div class="rec-section-label">${t("settings.section.app")}</div>
        <div class="card card--rows">
          ${navRow("Перенос из других сервисов", "import", "open-transfer")}
          ${navRow(t("settings.language"), "globe", "open-language")}
          ${navRow("Интерфейс", "palette", "open-interface")}
          ${navRow("Память устройства", "database", "open-storage")}
        </div>

        <div class="rec-section-label">Подписка</div>
        <div class="card card--rows">
          ${navRow("Infinity Music Premium", "crown", "open-premium")}
          ${navRow("Реферальная программа", "gift", "open-referral")}
        </div>

        <div class="rec-section-label">Помощь</div>
        <div class="card card--rows">
          ${navRow("Вопросы и ответы", "help", "open-doc", ' data-doc="faq"')}
          ${navRow("Поддержка Telegram", "headset", "open-support")}
        </div>

        <div class="rec-section-label">Документы</div>
        <div class="card card--rows">
          ${navRow("Политика конфиденциальности", "lock", "open-doc", ' data-doc="privacy"')}
          ${navRow("Публичная оферта", "doc", "open-doc", ' data-doc="offer"')}
          ${navRow("Лицензионное соглашение", "doc", "open-doc", ' data-doc="license"')}
          ${navRow("О приложении", "sparkles", "open-doc", ' data-doc="about"')}
        </div>
      `;
    }
    return { renderSettings };
  })();

  __m["screens/language.js"] = (function () {
    const { icon } = __m["components/icons.js"];
    const { LANGUAGES, getLanguage, isTranslated, t } = __m["i18n.js"];
    // Экран выбора языка (заготовка мультиязычности). Языки без перевода видны в
    // списке, но помечены — человек сразу понимает, что увидит английский.

    function renderLanguage() {
      const current = getLanguage();
      const rows = LANGUAGES.map((item) => {
        const pending = isTranslated(item.code)
          ? ""
          : `<div class="settings-row__hint">${t("language.pending")}</div>`;
        return `
          <button class="settings-row" data-action="set-language" data-code="${item.code}" style="width:100%">
            <div class="settings-row__label">
              <span class="lang-flag">${item.flag}</span>
              <span>${item.title}${pending}</span>
            </div>
            ${item.code === current ? icon("check") : ""}
          </button>
        `;
      }).join("");

      return `
        <div class="page-head" data-role="page-head">
          <button class="icon-btn" data-action="back" aria-label="${t("common.back")}">${icon("back")}</button>
          <span>${t("language.title")}</span>
        </div>
        <p class="muted" style="padding:0 16px 12px">${t("language.hint")}</p>
        <div class="card card--rows">${rows}</div>
      `;
    }
    return { renderLanguage };
  })();

  __m["screens/recommendations.js"] = (function () {
    const { icon } = __m["components/icons.js"];
    // Настройки рекомендаций (настроение / узнаваемость / язык). Выбор сохраняется
    // локально; серверная фильтрация микса под эти параметры — следующий блок.

    const MOODS = [
      { id: "happy", ic: "sun", label: "Счастливое" },
      { id: "sad", ic: "moon", label: "Грустное" },
      { id: "energetic", ic: "fire", label: "Энергичное" },
      { id: "calm", ic: "leaf", label: "Спокойное" },
      { id: "love", ic: "heart", label: "Любовь" },
    ];

    const RECOGNIZABILITY = [
      { id: "known", label: "Известные" },
      { id: "unknown", label: "Неизвестные" },
      { id: "new", label: "Новые" },
    ];

    const LANGUAGES = [
      { id: "russian", label: "Русская" },
      { id: "foreign", label: "Зарубежная" },
      { id: "instrumental", label: "Инструментальная" },
    ];

    function moodTile(mood, active) {
      return `
        <button class="mood-tile${active ? " is-active" : ""}" data-action="set-mood" data-value="${mood.id}">
          <span class="mood-tile__icon">${icon(mood.ic)}</span>
          <span class="mood-tile__label">${mood.label}</span>
        </button>
      `;
    }

    function pill(action, item, active) {
      return `
        <button class="pill${active ? " is-active" : ""}" data-action="${action}" data-value="${item.id}">
          ${item.label}
        </button>
      `;
    }

    function renderRecommendations(state) {
      const s = state.recDraft;

      return `
        <div class="page-head" data-role="page-head">
          <button class="icon-btn" data-action="back" aria-label="Назад">${icon("back")}</button>
          <span>Настройки Infinity Mix</span>
        </div>

        <div class="rec-section-label">Настроение</div>
        <div class="mood-grid h-scroll">
          ${MOODS.map((m) => moodTile(m, s.mood === m.id)).join("")}
        </div>

        <div class="rec-section-label">Тип</div>
        <div class="pill-row">
          ${RECOGNIZABILITY.map((r) => pill("set-recog", r, s.recognizability === r.id)).join("")}
        </div>

        <div class="rec-section-label">Язык музыки</div>
        <div class="pill-row">
          ${LANGUAGES.map((l) => pill("set-lang", l, s.language === l.id)).join("")}
        </div>

        <div class="rec-actions">
          <button class="btn btn--ghost" data-action="clear-rec">Очистить</button>
          <button class="btn btn--primary" data-action="apply-rec">Применить</button>
        </div>
      `;
    }
    return { renderRecommendations };
  })();

  __m["screens/recent.js"] = (function () {
    const { icon } = __m["components/icons.js"];
    const { renderTrackList } = __m["components/trackRow.js"];
    const { getRecentTracks } = __m["prefs.js"];
    function renderRecent(state) {
      const tracks = getRecentTracks();

      return `
        <div class="page-head" data-role="page-head">
          <button class="icon-btn" data-action="back" aria-label="Назад">${icon("back")}</button>
          <span>Недавно прослушанные</span>
        </div>

        ${
          tracks.length
            ? `<div class="card home-track-card">${renderTrackList(tracks, { context: "recent", state })}</div>`
            : '<div class="empty-state">Здесь появятся треки, которые вы слушали.</div>'
        }
      `;
    }
    return { renderRecent };
  })();

  __m["screens/artists.js"] = (function () {
    const { icon } = __m["components/icons.js"];
    const { escapeHtml } = __m["components/trackRow.js"];
    const { getFavoriteArtists } = __m["prefs.js"];
    // Исполнители (ТЗ §13-14): дедуплицированный список с сервера, тап открывает
    // треки исполнителя. Сердечко — «любимый исполнитель» для рекомендаций.

    function renderArtists(state) {
      const head = `
        <div class="page-head" data-role="page-head">
          <button class="icon-btn" data-action="back" aria-label="Назад">${icon("back")}</button>
          <span>Исполнители</span>
        </div>
      `;

      if (state.artistsStatus === "loading") {
        return `${head}<div class="empty-state">Загружаю…</div>`;
      }

      const artists = state.artists || [];
      if (!artists.length) {
        return `${head}<div class="empty-state">В базе пока нет исполнителей</div>`;
      }

      const favorites = new Set(getFavoriteArtists().map((a) => a.toLowerCase()));

      const list = artists
        .map((a) => {
          const active = favorites.has(a.name.toLowerCase());
          return `
            <div class="artist-row${active ? " is-fav" : ""}" data-action="open-artist" data-artist="${escapeHtml(a.name)}">
              <span class="artist-row__avatar">${escapeHtml((a.name[0] || "?").toUpperCase())}</span>
              <span class="artist-row__info">
                <span class="artist-row__name">${escapeHtml(a.name)}</span>
                <span class="artist-row__count">${a.track_count} треков</span>
              </span>
              <button class="artist-row__heart icon-btn" data-action="toggle-artist" data-artist="${escapeHtml(a.name)}" aria-label="В любимые">${icon("heart")}</button>
            </div>
          `;
        })
        .join("");

      return `
        ${head}
        <p class="page-hint">Отмечайте сердечком любимых — это улучшит рекомендации.</p>
        <div class="artist-list">${list}</div>
      `;
    }
    return { renderArtists };
  })();

  __m["screens/artistcard.js"] = (function () {
    const { icon } = __m["components/icons.js"];
    const { renderTrackList, escapeHtml } = __m["components/trackRow.js"];
    const { renderCover, sizedCover } = __m["components/cover.js"];
    // Карточка артиста (SPEC-КАТАЛОГ §2 + референсы Яндекс/VK): баннер, аватар,
    // жанры, подписка, последний релиз, топ треков, синглы, альбомы, похожие артисты.

    function heroStyle(card) {
      return card.banner_url
        ? ` style="background-image:linear-gradient(to bottom, rgba(15,15,16,.35), rgba(15,15,16,.95)), url('${escapeHtml(card.banner_url)}')"`
        : "";
    }

    function avatar(card) {
      if (card.photo_url) {
        return `<img class="artist-hero__avatar" src="${escapeHtml(card.photo_url)}" alt="" loading="lazy" />`;
      }
      const letter = escapeHtml((card.name.trim()[0] || "♪").toUpperCase());
      return `<div class="artist-hero__avatar artist-hero__avatar--letter">${letter}</div>`;
    }

    function latestReleaseBlock(track) {
      if (!track) return "";
      return `
        <div class="latest-release">
          <div class="latest-release__label">Последний релиз</div>
          <div class="latest-release__body" data-action="play-track" data-id="${track.id}">
            ${renderCover(track)}
            <div class="latest-release__info">
              <div class="track-title">${escapeHtml(track.title)}</div>
              <div class="track-artist">Сингл</div>
            </div>
            <button class="icon-btn latest-release__play" data-action="play-track" data-id="${track.id}">${icon("play")}</button>
          </div>
        </div>
      `;
    }

    function similarBlock(similar) {
      if (!similar || !similar.length) return "";
      const cards = similar
        .map((s) => {
          const avatarHtml = s.photo_url
            ? `<img class="similar-artist__avatar" src="${escapeHtml(s.photo_url)}" alt="" loading="lazy" />`
            : `<span class="similar-artist__avatar similar-artist__avatar--letter">${escapeHtml((s.name[0] || "♪").toUpperCase())}</span>`;
          return `
            <button class="similar-artist" data-action="open-artist" data-artist="${escapeHtml(s.name)}">
              ${avatarHtml}
              <span class="similar-artist__name">${escapeHtml(s.name)}</span>
            </button>
          `;
        })
        .join("");
      return `
        <div class="section-head"><span class="section-title">Похожие артисты</span></div>
        <div class="similar-artists">${cards}</div>
      `;
    }

    function renderArtistCard(state) {
      const head = `
        <div class="page-head" data-role="page-head">
          <button class="icon-btn" data-action="back" aria-label="Назад">${icon("back")}</button>
          <span>Исполнитель</span>
        </div>
      `;

      if (state.artistCardStatus === "loading" || !state.artistCard) {
        return `${head}<div class="empty-state">Загружаю…</div>`;
      }
      if (state.artistCardStatus === "error") {
        return `${head}<div class="empty-state">Не удалось загрузить карточку</div>`;
      }

      const card = state.artistCard;
      const name = escapeHtml(card.name);

      const genresBlock = card.genres.length
        ? `<div class="chip-cloud artist-hero__genres">${card.genres
            .map((g) => `<span class="search-chip">${escapeHtml(g)}</span>`)
            .join("")}</div>`
        : "";

      const description = card.description
        ? `<p class="artist-card__desc">${escapeHtml(card.description)}</p>`
        : "";

      // Подписка — только если у артиста есть сущность в базе (artist_id)
      const followBtn = card.artist_id
        ? `<button class="btn ${card.following ? "btn--ghost" : "btn--outline"} artist-hero__follow" data-action="toggle-follow" data-id="${card.artist_id}">
             ${card.following ? icon("check") + " Вы подписаны" : icon("plus") + " Подписаться"}
           </button>`
        : "";

      const actions = card.track_count
        ? `
          <div class="coll-hero__actions">
            <button class="btn btn--primary" data-action="artist-play-all" data-artist="${name}">${icon("play")} Слушать всё</button>
            <button class="btn btn--ghost" data-action="artist-play-similar" data-artist="${name}">${icon("radio")} Слушать похожее</button>
          </div>
        `
        : "";

      const topBlock = card.top_tracks.length
        ? `
          <div class="section-head section-head--between">
            <span class="section-title">Топ треков</span>
            <button class="link-more" data-action="open-artist-tracks" data-artist="${name}">Все ${card.track_count}</button>
          </div>
          <div class="card">${renderTrackList(card.top_tracks.slice(0, 5), { context: "collection", state })}</div>
        `
        : '<div class="empty-state">Треки этого артиста ещё загружаются в базу</div>';

      const singlesBlock = card.singles && card.singles.length
        ? `
          <div class="section-head"><span class="section-title">Синглы</span></div>
          <div class="card">${renderTrackList(card.singles, { context: "collection", state })}</div>
        `
        : "";

      const albumsBlock = card.albums.length
        ? `
          <div class="section-head"><span class="section-title">Альбомы</span></div>
          <div class="artist-albums">${card.albums
            .map(
              (a) => `
                <button class="artist-album" data-action="open-album" data-name="${escapeHtml(a.name)}">
                  ${
                    a.cover_url
                      ? `<img class="artist-album__cover" src="${escapeHtml(sizedCover(a.cover_url))}" alt="" loading="lazy" />`
                      : `<span class="artist-album__cover artist-album__cover--letter">${escapeHtml((a.name[0] || "♪").toUpperCase())}</span>`
                  }
                  <span class="artist-album__name">${escapeHtml(a.name)}</span>
                  <span class="artist-album__count">${a.track_count} треков</span>
                </button>
              `
            )
            .join("")}</div>
        `
        : "";

      return `
        ${head}
        <div class="artist-hero"${heroStyle(card)}>
          ${avatar(card)}
          <div class="artist-hero__name">${name}</div>
          ${genresBlock}
          ${followBtn}
          ${actions}
        </div>
        ${latestReleaseBlock(card.latest_release)}
        ${description}
        ${topBlock}
        ${singlesBlock}
        ${albumsBlock}
        ${similarBlock(card.similar)}
      `;
    }
    return { renderArtistCard };
  })();

  __m["screens/myartists.js"] = (function () {
    const { icon } = __m["components/icons.js"];
    const { escapeHtml } = __m["components/trackRow.js"];
    // «Мои артисты» — подписки пользователя (референс: раздел библиотеки).
    // Тап по строке открывает карточку артиста.

    function renderMyArtists(state) {
      const head = `
        <div class="page-head" data-role="page-head">
          <button class="icon-btn" data-action="back" aria-label="Назад">${icon("back")}</button>
          <span>Мои артисты</span>
        </div>
      `;

      if (state.myArtistsStatus === "loading") {
        return `${head}<div class="empty-state">Загружаю…</div>`;
      }

      const artists = state.myArtists || [];
      if (!artists.length) {
        return `${head}<div class="empty-state">Вы ещё не подписаны ни на одного артиста. Откройте карточку артиста и нажмите «Подписаться».</div>`;
      }

      const list = artists
        .map((a) => {
          const avatarHtml = a.photo_url
            ? `<img class="artist-row__avatar-img" src="${escapeHtml(a.photo_url)}" alt="" loading="lazy" />`
            : `<span class="artist-row__avatar">${escapeHtml((a.name[0] || "?").toUpperCase())}</span>`;
          return `
            <div class="artist-row" data-action="open-artist" data-artist="${escapeHtml(a.name)}">
              ${avatarHtml}
              <span class="artist-row__info">
                <span class="artist-row__name">${escapeHtml(a.name)}</span>
                <span class="artist-row__count">${a.track_count} треков</span>
              </span>
              <button class="artist-row__heart icon-btn" data-action="unfollow-artist" data-id="${a.id}" aria-label="Отписаться">${icon("check")}</button>
            </div>
          `;
        })
        .join("");

      return `${head}<div class="artist-list">${list}</div>`;
    }
    return { renderMyArtists };
  })();

  __m["screens/docs.js"] = (function () {
    const { icon } = __m["components/icons.js"];
    // Статические разделы (ТЗ §17-20): полноценные FAQ, политика, лицензия,
    // «О приложении» с аккуратным блоком версии.

    const APP_VERSION = "2.0";

    const DOCS = {
      faq: {
        title: "Вопросы и ответы",
        blocks: [
          [
            "Как слушать музыку?",
            "Нажмите «Слушать Infinity Mix» на главной — соберётся персональная очередь, треки будут переключаться сами. Любой трек из поиска, библиотеки или плейлиста тоже запускает очередь: после него продолжит играть остальной список.",
          ],
          [
            "Что такое Infinity Mix?",
            "Это бесконечный микс под ваши предпочтения. Нажмите «Настроить» внутри блока Infinity Mix и выберите настроение, тип и язык музыки — микс пересоберётся под выбор. Настройки можно менять сколько угодно раз.",
          ],
          [
            "Как добавить трек к себе?",
            "Нажмите «+» рядом с треком — он попадёт в «Мои треки». Убрать трек можно тем же способом или через режим редактирования (карандаш) на странице «Мои треки».",
          ],
          [
            "Как скачать трек?",
            "Нажмите «Скачать» в карточке трека или в меню «…». Бот пришлёт аудиофайл вам в чат Telegram — он останется там навсегда и будет доступен офлайн средствами Telegram.",
          ],
          [
            "Что такое «Сохранить офлайн»?",
            "Premium-функция: трек сохраняется внутри приложения и играет мгновенно даже без интернета. Список сохранённых — на вкладке «Скачанные» в «Моих треках».",
          ],
          [
            "Как создать плейлист?",
            "Откройте «Плейлисты» с главной или из библиотеки и нажмите «Создать плейлист». На бесплатном тарифе доступно до 5 плейлистов, с Premium — без ограничений.",
          ],
          [
            "Как загрузить свой трек?",
            "Двумя способами: в приложении — «Библиотека → Загрузить трек» (выберите файл, укажите название и исполнителя); или в чате бота — меню «Загрузить трек», где принимается файл или ссылка на YouTube Music / SoundCloud. Всегда указывайте исполнителя — иначе трек станет «Неизвестным».",
          ],
          [
            "Как перенести музыку из другого сервиса?",
            "«Библиотека → Перенести из сервисов» или команда /transfer в боте. Пришлите ссылку на плейлист Spotify или Яндекс.Музыки — либо список треков строками «Артист — Название» (так переносится музыка из ВК). Найдём в базе, чего нет — загрузим.",
          ],
          [
            "Что даёт Premium?",
            "Без рекламы, офлайн-прослушивание, перенос плейлистов пачкой, безлимитные плейлисты и загрузки, эквалайзер и таймер сна, добавление текстов песен. Цена месяца — на экране Premium, годовая подписка выгоднее. Первые 7 дней — бесплатно, без карты: пробный период включается сам при первом открытии приложения.",
          ],
          [
            "Как работает реферальная программа?",
            "Приглашайте друзей по личной ссылке из профиля — уже за первого друга неделя Premium, дальше больше, вплоть до пожизненной подписки за 5000 друзей. Подробности — в разделе «Реферальная программа».",
          ],
          [
            "Как вынести плеер на рабочий стол?",
            // Адрес — из текущей страницы, а не строкой: домен меняется при переезде.
            `iPhone: откройте ${location.host} в Safari → «Поделиться» → «На экран „Домой“». Android: откройте сайт в Chrome → меню «⋮» → «Добавить на главный экран». Появится иконка как у обычного приложения — музыку можно слушать, не заходя в Telegram.`,
          ],
          [
            "Играет ли музыка в фоне?",
            "Да. Приложение можно свернуть — воспроизведение продолжится. Останавливается только при полном закрытии приложения. Свёрнутым оно не мешает и не расходует лишнего.",
          ],
          [
            "Не играет трек — что делать?",
            "Проверьте интернет и попробуйте другой трек. Если проблема повторяется — напишите в «Поддержка Telegram» в настройках, укажите название трека.",
          ],
        ],
      },
      privacy: {
        title: "Политика конфиденциальности",
        blocks: [
          [
            "1. Общие положения",
            "Настоящая политика описывает, какие данные обрабатывает музыкальный сервис Infinity Music (далее — «Сервис») и как они используются. Открывая Mini App или используя бота, вы соглашаетесь с этой политикой.",
          ],
          [
            "2. Какие данные мы собираем",
            "Данные Telegram-профиля: идентификатор, имя, username и фото профиля — их передаёт Telegram при авторизации. История действий в Сервисе: прослушивания, скачивания, поисковые запросы, добавления в библиотеку и плейлисты. Технические данные: тип устройства и версия клиента — для диагностики ошибок.",
          ],
          [
            "3. Зачем эти данные нужны",
            "Авторизация без пароля, персональные рекомендации (Infinity Mix), статистика популярных запросов, работа реферальной программы и достижений, начисление и продление Premium.",
          ],
          [
            "4. Платежи",
            "Оплата Premium проходит через платёжного провайдера ЮKassa. Сервис не получает и не хранит данные банковских карт — только факт и сумму платежа для активации подписки.",
          ],
          [
            "5. Кому передаются данные",
            "Никому. Данные не продаются и не передаются третьим лицам, кроме случаев, прямо предусмотренных законом.",
          ],
          [
            "6. Хранение и защита",
            "Данные хранятся на защищённых серверах. Доступ к ним ограничен и есть только у администрации Сервиса. Настройки рекомендаций и история прослушиваний частично хранятся локально на вашем устройстве.",
          ],
          [
            "7. Ваши права",
            "Вы можете запросить удаление своих данных: напишите в «Поддержка Telegram» из настроек. Аккаунт и связанные данные будут удалены, кроме сведений, обязательных к хранению по закону.",
          ],
          [
            "8. Изменения политики",
            "Актуальная редакция всегда доступна в этом разделе. Продолжение использования Сервиса после изменений означает согласие с новой редакцией.",
          ],
        ],
      },
      license: {
        title: "Лицензионное соглашение",
        blocks: [
          [
            "1. О приложении",
            "Infinity Music — музыкальный сервис внутри Telegram: библиотека, поиск, плейлисты, персональные рекомендации, тексты песен и Premium-подписка. Сервис предоставляется «как есть» для личного некоммерческого использования.",
          ],
          [
            "2. Права пользователя",
            "Вы вправе бесплатно слушать музыку из общей базы, вести библиотеку и плейлисты, скачивать треки себе в чат, участвовать в реферальной программе. С Premium дополнительно доступны офлайн-режим, безлимитные плейлисты и загрузки, добавление текстов.",
          ],
          [
            "3. Ограничения",
            "Запрещается: массовое автоматизированное скачивание контента; перепродажа или передача доступа третьим лицам; загрузка контента, права на который вам не принадлежат; использование Сервиса для нарушения прав правообладателей или законодательства.",
          ],
          [
            "4. Контент и права",
            "Права на музыкальные произведения принадлежат их правообладателям. Сервис обеспечивает техническую возможность воспроизведения. По требованию правообладателя контент удаляется — обратитесь в поддержку.",
          ],
          [
            "5. Подписка Premium",
            "Premium активируется после оплаты и действует выбранный срок. Базовый тариф — 49 ₽ в месяц с автоматическим продлением: раз в месяц с привязанного способа оплаты списывается стоимость следующего периода, пока вы не отключите автопродление в настройках. При продлении оставшиеся дни суммируются. Возврат за неиспользованный период не предусмотрен, кроме случаев, установленных законом.",
          ],
          [
            "6. Ответственность",
            "Сервис не гарантирует непрерывную доступность и не отвечает за убытки, возникшие из-за перерывов в работе. Пользователь несёт ответственность за контент, который загружает. Администрация вправе ограничить доступ при нарушении настоящего соглашения.",
          ],
        ],
      },
      offer: {
        title: "Публичная оферта",
        blocks: [
          [
            "1. Общие положения",
            "Настоящая оферта — предложение заключить договор на предоставление доступа к Premium-функциям сервиса Infinity Music. Исполнитель — самозанятый (плательщик налога на профессиональный доход). Оплачивая подписку, вы принимаете условия оферты и политики конфиденциальности в полном объёме.",
          ],
          [
            "2. Предмет и стоимость",
            "Premium открывает офлайн-режим, безлимитные плейлисты и загрузки, добавление текстов и отключение обязательных подписок. Стоимость — 49 ₽ за календарный месяц. Доступны также тарифы на 3/6/12 месяцев и «навсегда» по ценам, указанным в приложении.",
          ],
          [
            "3. Автоматическое продление",
            "Подписка продлевается автоматически: за сутки-двое до окончания оплаченного периода со способа оплаты, привязанного при первом платеже, списывается стоимость следующего месяца (49 ₽). Списания продолжаются, пока вы не отключите автопродление в настройках или не обратитесь в поддержку. Оформляя подписку, вы даёте согласие на регулярные списания указанной суммы.",
          ],
          [
            "4. Отмена и возврат",
            "Отключить автопродление можно в любой момент в настройках приложения — доступ сохранится до конца оплаченного периода. Возврат средств за уже начатый период не производится, кроме случаев, предусмотренных законодательством РФ.",
          ],
          [
            "5. Оплата",
            "Платежи проводит платёжный сервис ЮKassa. Данные банковской карты Исполнителю не передаются и не хранятся у него — их обрабатывает платёжный сервис по стандартам безопасности PCI DSS.",
          ],
          [
            "6. Контакты",
            "По вопросам подписки, возврата и работы сервиса — обращайтесь в поддержку внутри приложения.",
          ],
        ],
      },
      about: {
        title: "О приложении",
        blocks: [], // рендерится отдельным макетом ниже
      },
    };

    function renderAbout() {
      return `
        <div class="about-hero">
          <div class="about-hero__logo">🎧</div>
          <div class="about-hero__name">Infinity Music</div>
          <div class="about-hero__version">Версия ${APP_VERSION}</div>
        </div>
        <div class="card card--rows">
          <div class="settings-row"><div class="settings-row__label">${icon("note")}Музыкальный сервис в Telegram</div></div>
          <div class="settings-row"><div class="settings-row__label">${icon("sparkles")}Рекомендации, плейлисты, тексты песен</div></div>
          <div class="settings-row"><div class="settings-row__label">${icon("crown")}Premium: без рекламы и офлайн</div></div>
        </div>
        <div class="rec-section-label">Полезно знать</div>
        <div class="card card--rows">
          <div class="settings-row"><div class="settings-row__label">${icon("import")}Можно вынести на рабочий стол — как обычное приложение</div></div>
          <div class="settings-row"><div class="settings-row__label">${icon("play")}Играет в фоне — сверните, музыка не остановится</div></div>
        </div>
        <button class="settings-row" data-action="open-support" style="width:100%;margin-top:10px">
          <div class="settings-row__label">${icon("headset")}Поддержка Telegram</div>
          ${icon("chevron")}
        </button>
      `;
    }

    function renderDocs(state) {
      const doc = DOCS[state.docKey] || DOCS.about;

      const head = `
        <div class="page-head" data-role="page-head">
          <button class="icon-btn" data-action="back" aria-label="Назад">${icon("back")}</button>
          <span>${doc.title}</span>
        </div>
      `;

      if (state.docKey === "about") {
        return `${head}${renderAbout()}`;
      }

      const body = doc.blocks
        .map(
          ([heading, text]) => `
            <div class="doc-block">
              <div class="doc-block__heading">${heading}</div>
              <div class="doc-block__text">${text}</div>
            </div>
          `
        )
        .join("");

      return `${head}<div class="doc-body">${body}</div>`;
    }
    return { APP_VERSION, renderDocs };
  })();

  __m["screens/achievements.js"] = (function () {
    const { icon } = __m["components/icons.js"];
    function achievementCard(a) {
      const pct = a.target ? Math.min(100, Math.round((a.progress / a.target) * 100)) : 0;
      const reward = a.reward_days
        ? `<span class="ach-card__reward">+${a.reward_days} ${dayWord(a.reward_days)} Premium</span>`
        : "";
      return `
        <div class="ach-card${a.unlocked ? " is-unlocked" : ""}">
          <span class="ach-card__emoji">${a.emoji}</span>
          <div class="ach-card__body">
            <div class="ach-card__title">${a.title} ${reward}</div>
            ${
              a.unlocked
                ? '<div class="ach-card__done">Получено</div>'
                : `<div class="ach-card__bar"><span style="width:${pct}%"></span></div>
                   <div class="ach-card__progress">${a.progress} / ${a.target}</div>`
            }
          </div>
        </div>
      `;
    }

    function dayWord(days) {
      const last = days % 10;
      const two = days % 100;
      if (two >= 11 && two <= 14) return "дней";
      if (last === 1) return "день";
      if (last >= 2 && last <= 4) return "дня";
      return "дней";
    }

    function renderAchievements(state) {
      const head = `
        <div class="page-head" data-role="page-head">
          <button class="icon-btn" data-action="back" aria-label="Назад">${icon("back")}</button>
          <span>Достижения</span>
        </div>
      `;

      const profile = state.profile;
      if (!profile) {
        return `${head}<div class="empty-state">Откройте профиль, чтобы загрузить достижения.</div>`;
      }

      const categories = [];
      const byCategory = new Map();
      for (const a of profile.achievements) {
        if (!byCategory.has(a.category)) {
          byCategory.set(a.category, []);
          categories.push(a.category);
        }
        byCategory.get(a.category).push(a);
      }

      const sections = categories
        .map(
          (cat) => `
            <div class="rec-section-label">${cat}</div>
            <div class="ach-list">${byCategory.get(cat).map(achievementCard).join("")}</div>
          `
        )
        .join("");

      const earned = profile.achievements
        .filter((a) => a.unlocked)
        .reduce((sum, a) => sum + (a.reward_days || 0), 0);
      const pending = profile.achievements
        .filter((a) => !a.unlocked)
        .reduce((sum, a) => sum + (a.reward_days || 0), 0);

      return `
        ${head}
        <div class="ach-summary">Открыто ${profile.achievements_unlocked} из ${profile.achievements_total}</div>
        <div class="card card--flat ach-bank">
          <div><b>${earned}</b> ${dayWord(earned)} Premium уже заработано</div>
          ${pending ? `<div class="hint-text">Ещё ${pending} ${dayWord(pending)} ждут — выполняйте достижения</div>` : ""}
        </div>
        ${sections}
      `;
    }
    return { dayWord, renderAchievements };
  })();

  __m["screens/lyrics.js"] = (function () {
    const { icon } = __m["components/icons.js"];
    const { escapeHtml } = __m["components/trackRow.js"];
    // Текст песни (ТЗ §8): открывается сразу, дизайн по VK — крупный читаемый текст.
    // Добавлять и править тексты могут только админы (решение владельца 19.09):
    // текст общий для всех слушателей, правка перезаписывает его целиком.

    const SOURCE_LABEL = { lrclib: "найдено автоматически", user: "добавлено слушателями", admin: "добавлено администратором" };

    function editor(state, initial) {
      return `
        <textarea class="lyrics-input" data-role="lyrics-input" rows="12"
          placeholder="Вставьте текст песни построчно…">${escapeHtml(initial)}</textarea>
        <div class="rec-actions">
          ${
            state.lyrics && state.lyrics.found
              ? '<button class="btn btn--ghost" data-action="lyrics-cancel">Отмена</button>'
              : ""
          }
          <button class="btn btn--primary" data-action="lyrics-save">Сохранить</button>
        </div>
      `;
    }

    function renderLyrics(state) {
      const track = state.lyricsTrack;
      // Право правки сообщает сервер — он же его и проверяет при сохранении
      const canEdit = Boolean(state.lyrics && state.lyrics.can_edit);

      const head = `
        <div class="page-head" data-role="page-head">
          <button class="icon-btn" data-action="back" aria-label="Назад">${icon("back")}</button>
          <span>Текст песни</span>
        </div>
        ${
          track
            ? `<div class="lyrics-track">
                 <div class="lyrics-track__title">${escapeHtml(track.title)}</div>
                 <div class="lyrics-track__artist">${escapeHtml(track.artist)}</div>
               </div>`
            : ""
        }
      `;

      if (state.lyricsStatus === "loading") {
        return `${head}<div class="empty-state">Ищу текст…</div>`;
      }

      const lyrics = state.lyrics;

      if (state.lyricsEditing && canEdit) {
        return `${head}${editor(state, lyrics && lyrics.text ? lyrics.text : "")}`;
      }

      if (lyrics && lyrics.found) {
        return `
          ${head}
          <pre class="lyrics-text">${escapeHtml(lyrics.text)}</pre>
          <div class="lyrics-meta">${SOURCE_LABEL[lyrics.source] || ""}</div>
          ${
            canEdit
              ? `<button class="btn btn--ghost btn--block" data-action="lyrics-edit" style="margin-top:12px">${icon("pencil")} Изменить текст</button>`
              : ""
          }
        `;
      }

      return `
        ${head}
        <p class="page-hint">Текста этой песни пока нет в базе.</p>
        ${canEdit ? editor(state, "") : ""}
      `;
    }
    return { renderLyrics };
  })();

  __m["screens/downloads.js"] = (function () {
    const { icon } = __m["components/icons.js"];
    const { renderTrackList } = __m["components/trackRow.js"];
    const { offlineTracks, offlineSupported } = __m["offline.js"];
    function renderDownloads(state) {
      const tracks = offlineTracks();
      const head = `
        <div class="page-head" data-role="page-head">
          <button class="icon-btn" data-action="back" aria-label="Назад">${icon("back")}</button>
          <span>Загрузки</span>
        </div>
      `;

      if (!offlineSupported()) {
        return `${head}<div class="empty-state">Офлайн-сохранение недоступно в этом клиенте.</div>`;
      }
      if (!tracks.length) {
        return `
          ${head}
          <p class="page-hint">Сохраняйте треки офлайн через «Ещё» → «Сохранить офлайн» (нужен Premium). Они играют мгновенно и без повторной загрузки.</p>
        `;
      }

      return `
        ${head}
        <div class="card home-track-card">${renderTrackList(tracks, { context: "offline", state })}</div>
      `;
    }
    return { renderDownloads };
  })();

  __m["screens/playlists.js"] = (function () {
    const { icon } = __m["components/icons.js"];
    const { escapeHtml } = __m["components/trackRow.js"];
    // Список плейлистов по референсу VK Music (ТЗ §6): строки с квадратной обложкой,
    // сверху — «Создать плейлист» (инлайн-форма без всплывающих окон).

    function playlistCover(title) {
      const letter = escapeHtml((title || "?").trim()[0] || "?").toUpperCase();
      return `<span class="pl-cover">${letter}</span>`;
    }

    function renderPlaylists(state) {
      const head = `
        <div class="page-head" data-role="page-head">
          <button class="icon-btn" data-action="back" aria-label="Назад">${icon("back")}</button>
          <span>Плейлисты</span>
        </div>
      `;

      if (state.playlistsStatus === "loading") {
        return `${head}<div class="empty-state">Загружаю…</div>`;
      }

      // Сеть отвалилась — честный отказ с кнопкой. Раньше экран показывал
      // «Плейлистов пока нет», то есть врал про пустоту вместо ошибки (19.09)
      if (state.playlistsStatus === "error") {
        return `
          ${head}
          <div class="empty-state">Не удалось загрузить плейлисты.</div>
          <button class="btn btn--primary btn--block" data-action="open-playlists">Повторить</button>
        `;
      }

      const createRow = state.playlistCreating
        ? `
          <div class="pl-create-form">
            <input type="text" data-role="playlist-title" placeholder="Название плейлиста" maxlength="100" />
            <button class="btn btn--primary" data-action="playlist-create-submit">Создать</button>
            <button class="btn btn--ghost" data-action="playlist-create-cancel">Отмена</button>
          </div>
        `
        : `
          <button class="pl-row pl-row--create" data-action="playlist-create">
            <span class="pl-cover pl-cover--create">${icon("plus")}</span>
            <span class="pl-row__title" style="color:var(--text-accent)">Создать плейлист</span>
          </button>
        `;

      const playlists = state.playlists || [];
      const rows = playlists
        .map(
          (p) => `
            <button class="pl-row" data-action="open-playlist" data-id="${p.id}" data-title="${escapeHtml(p.title)}">
              ${playlistCover(p.title)}
              <span class="pl-row__text">
                <span class="pl-row__title">${escapeHtml(p.title)}</span>
                <span class="pl-row__sub">${p.track_count} треков</span>
              </span>
              ${icon("chevron")}
            </button>
          `
        )
        .join("");

      return `
        ${head}
        ${createRow}
        ${rows || '<div class="empty-state">Плейлистов пока нет — создайте первый.</div>'}
      `;
    }
    return { renderPlaylists };
  })();

  __m["screens/albums.js"] = (function () {
    const { icon } = __m["components/icons.js"];
    const { escapeHtml } = __m["components/trackRow.js"];
    function renderAlbums(state) {
      const head = `
        <div class="page-head" data-role="page-head">
          <button class="icon-btn" data-action="back" aria-label="Назад">${icon("back")}</button>
          <span>Альбомы</span>
        </div>
      `;

      if (state.albumsStatus === "loading") {
        return `${head}<div class="empty-state">Загружаю…</div>`;
      }

      const albums = state.albums || [];
      if (!albums.length) {
        return `${head}<div class="empty-state">Альбомов пока нет — у треков не заполнено поле альбома.</div>`;
      }

      const rows = albums
        .map(
          (a) => `
            <button class="quick-tile" data-action="open-album" data-name="${escapeHtml(a.name)}">
              <span class="quick-tile__icon">${icon("album")}</span>
              <span class="quick-tile__text">
                <span class="quick-tile__title">${escapeHtml(a.name)}</span>
                <span class="quick-tile__sub">${a.track_count} треков</span>
              </span>
            </button>
          `
        )
        .join("");

      return `${head}<div class="quick-access">${rows}</div>`;
    }
    return { renderAlbums };
  })();

  __m["screens/collection.js"] = (function () {
    const { icon } = __m["components/icons.js"];
    const { renderTrackList, escapeHtml } = __m["components/trackRow.js"];
    const { renderCover, sizedCover } = __m["components/cover.js"];
    // Страница плейлиста/альбома/исполнителя по референсу VK Music (ТЗ §6):
    // крупная обложка, название, счётчик и длительность, кнопки Слушать/Перемешать.

    const TYPE_LABEL = { playlist: "Плейлист", album: "Альбом", artist: "Исполнитель", genre: "Жанр" };

    function totalDuration(tracks) {
      const total = tracks.reduce((sum, t) => sum + (t.duration || 0), 0);
      const minutes = Math.round(total / 60);
      if (minutes < 60) return `${minutes} мин`;
      return `${Math.floor(minutes / 60)} ч ${minutes % 60} мин`;
    }

    function formatDuration(seconds) {
      const s = Math.max(0, Math.round(seconds || 0));
      return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
    }

    // Живые треки альбома (16.09): играют по номеру, а не по id — у них id «live:…»
    function renderLiveRows(items) {
      return items
        .map(
          (item, i) => `
            <div class="track-row" data-action="play-album-live" data-index="${i}">
              ${renderCover({ ...item, id: item.ref })}
              <div class="track-info">
                <div class="track-title">${i + 1}. ${escapeHtml(item.title)}</div>
                <div class="track-artist">${escapeHtml(item.artist)} · ${formatDuration(item.duration)}</div>
              </div>
            </div>
          `
        )
        .join("");
    }

    function renderCollection(state) {
      const title = state.collectionTitle || "Подборка";
      const head = `
        <div class="page-head" data-role="page-head">
          <button class="icon-btn" data-action="back" aria-label="Назад">${icon("back")}</button>
          <span>${TYPE_LABEL[state.collectionType] || "Подборка"}</span>
        </div>
      `;

      if (state.collectionStatus === "loading") {
        return `${head}<div class="empty-state">Загружаю…</div>`;
      }

      const tracks = state.collectionTracks || [];
      if (!tracks.length) {
        return `${head}<div class="empty-state">Здесь пока пусто.</div>`;
      }

      const letter = escapeHtml(title.trim()[0] || "♪").toUpperCase();
      const cover = state.collectionCover
        ? `<img class="coll-hero__cover" src="${escapeHtml(sizedCover(state.collectionCover, true))}" alt="" />`
        : `<div class="coll-hero__cover">${letter}</div>`;
      const live = state.collectionLive || [];
      const addAll = state.collectionAlbumId
        ? `<button class="btn btn--ghost" data-action="album-add-all">${icon("plus")} Добавить весь альбом</button>`
        : "";

      return `
        ${head}
        <div class="coll-hero">
          ${cover}
          <div class="coll-hero__title">${escapeHtml(title)}</div>
          <div class="coll-hero__meta">${tracks.length} треков · ${totalDuration(tracks)}</div>
          <div class="coll-hero__actions">
            <button class="btn btn--primary" data-action="collection-play">${icon("play")} Слушать</button>
            <button class="btn btn--ghost" data-action="collection-shuffle">${icon("shuffle")} Перемешать</button>
            ${addAll}
          </div>
        </div>
        <div class="card home-track-card">${
          live.length ? renderLiveRows(live) : renderTrackList(tracks, { context: "collection", state })
        }</div>
      `;
    }
    return { renderCollection };
  })();

  __m["screens/referral.js"] = (function () {
    const { icon } = __m["components/icons.js"];
    const { escapeHtml } = __m["components/trackRow.js"];
    const { dayWord } = __m["screens/achievements.js"];
    // Реферальная программа (ТЗ §23): описание, принцип работы, награды, прогресс.
    // Пороги наград зеркалят REFERRAL_MILESTONES бэкенда (services/gamification.py).

    // Пороги приходят с сервера (profile.referral.milestones) — своей копии здесь
    // больше нет. Раньше список был захардкожен неурезанными днями, а баннер
    // ближайшей награды показывал урезанные: приложение и бот расходились в цифрах.

    const STEPS = [
      "Поделитесь личной ссылкой с другом",
      "Друг открывает бота по вашей ссылке",
      "Награда начисляется автоматически",
    ];

    // Верхний порог — «Infinity Premium», а не «36500 дней»: столько дней стоит в
    // REFERRAL_MILESTONES как техническая запись «навсегда».
    const LIFETIME_DAYS = 36500;

    function prizeText(days) {
      return days >= LIFETIME_DAYS ? "Infinity Premium" : `${days} ${dayWord(days)} Premium`;
    }

    function rewardsList(profile) {
      const milestones = profile && profile.referral.milestones ? profile.referral.milestones : [];
      const invited = profile ? profile.referral.invited : 0;
      return milestones
        .map((r) => {
          const done = invited >= r.friends;
          return `
          <div class="ref-reward${done ? " is-done" : ""}">
            <span class="ref-reward__check">${icon(done ? "check" : "gift")}</span>
            <span class="ref-reward__friends">${r.friends} ${r.friends === 1 ? "друг" : r.friends < 5 ? "друга" : "друзей"}</span>
            <span class="ref-reward__prize">${prizeText(r.days)}</span>
          </div>
        `;
        })
        .join("");
    }

    function progressCard(profile) {
      if (!profile) {
        return '<div class="empty-state">Загружаю данные…</div>';
      }
      const ref = profile.referral;
      const rank = ref.rank;
      const next = ref.next_rank;
      const threshold = next ? ref.invited + ref.to_next : ref.invited || 1;
      const pct = Math.min(100, Math.round((ref.invited / threshold) * 100));

      return `
        <div class="card ref-progress">
          <div class="ref-progress__row">
            <span class="ref-progress__count">${ref.invited}</span>
            <span class="ref-progress__label">приглашено</span>
            ${rank ? `<span class="rank-badge">${rank.emoji} ${rank.title}</span>` : ""}
          </div>
          ${
            next
              ? `<div class="rank-progress__text">До ранга ${next.emoji} ${next.title} — ещё ${ref.to_next}</div>
                 <div class="rank-progress__bar"><span style="width:${pct}%"></span></div>`
              : rank
                ? '<div class="rank-progress__text">Максимальный ранг достигнут 👑</div>'
                : ""
          }
        </div>
      `;
    }

    // Ближайшая награда крупно: «ещё 1 друг — и +7 дней» работает лучше списка порогов
    function nextRewardBanner(profile) {
      if (!profile) return "";
      const { to_next_reward: left, next_reward_days: days } = profile.referral;
      if (!left || !days) return "";
      return `
        <div class="ref-next">
          <div class="ref-next__title">Ещё ${left} ${left === 1 ? "друг" : left < 5 ? "друга" : "друзей"} — и ${prizeText(days)}</div>
          <div class="ref-next__sub">Награда придёт автоматически</div>
        </div>
      `;
    }

    function leaderboard(state) {
      const rows = state.referralTop || [];
      if (!rows.length) return "";
      const medals = ["🥇", "🥈", "🥉"];
      const items = rows
        .map(
          (row, i) => `
            <div class="leader-row">
              <span class="leader-row__place">${medals[i] || i + 1}</span>
              <span class="leader-row__name">${escapeHtml(row.name)}</span>
              <span class="leader-row__count">${row.invited}</span>
            </div>
          `
        )
        .join("");
      return `
        <div class="rec-section-label">Топ приглашающих</div>
        <div class="card card--flat leader-list">${items}</div>
      `;
    }

    function renderReferral(state) {
      const profile = state.profile;
      const link = profile ? profile.referral.link : "";

      const steps = STEPS.map(
        (text, i) => `
          <div class="ref-step">
            <span class="ref-step__num">${i + 1}</span>
            <span class="ref-step__text">${text}</span>
          </div>
        `
      ).join("");

      return `
        <div class="page-head" data-role="page-head">
          <button class="icon-btn" data-action="back" aria-label="Назад">${icon("back")}</button>
          <span>Реферальная программа</span>
        </div>

        ${nextRewardBanner(profile)}
        ${progressCard(profile)}
        ${leaderboard(state)}

        <div class="rec-section-label">Как это работает</div>
        <div class="card card--rows ref-steps">${steps}</div>

        <div class="rec-section-label">Награды</div>
        <div class="card ref-rewards">${rewardsList(profile)}</div>

        <div class="rec-actions" style="margin-top:16px">
          ${link ? `<button class="btn btn--ghost" data-action="copy-referral" data-link="${escapeHtml(link)}">${icon("copy")} Скопировать</button>` : ""}
          <button class="btn btn--primary" data-action="invite-friend">${icon("share")} Пригласить</button>
        </div>
      `;
    }
    return { renderReferral };
  })();

  __m["screens/premium.js"] = (function () {
    const { icon } = __m["components/icons.js"];
    // Экран Premium с тарифами (ТЗ §24): 1/3/6/12 месяцев, годовой выделен как
    // самый выгодный. Цена = базовая цена месяца × месяцы (со скидкой пригласившего).

    // months=1200 — тариф «навсегда» (совпадает с FOREVER_MONTHS на бэкенде)
    const FOREVER_MONTHS = 1200;
    const FOREVER_PRICE = 10000;

    const PLANS = [
      { months: 1, label: "1 месяц" },
      { months: 3, label: "3 месяца" },
      { months: 6, label: "6 месяцев" },
      { months: 12, label: "12 месяцев" },
      { months: FOREVER_MONTHS, label: "Навсегда" },
    ];

    // Плюшки с описанием — чтобы человек видел, за что платит
    const PERKS = [
      ["sparkles", "Без рекламы", "Ни баннеров, ни пауз — только музыка"],
      ["download", "Офлайн-режим", "Скачивайте треки и слушайте без интернета"],
      ["import", "Перенос пачкой", "Целые плейлисты и профили из Spotify, Яндекса, ВК и SoundCloud"],
      ["playlist", "Без лимитов", "Сколько угодно плейлистов и загрузок своих треков"],
      ["sliders", "Эквалайзер и таймер сна", "7 полос, 20 пресетов, засыпайте под музыку"],
      ["lyrics", "Тексты песен", "Добавляйте и редактируйте тексты любимых треков"],
      ["gift", "Дни в подарок", "Достижения и друзья приносят ещё больше Premium"],
    ];

    function planPrice(state, months) {
      if (months >= FOREVER_MONTHS) {
        return { full: FOREVER_PRICE, effective: FOREVER_PRICE, discount: 0 };
      }
      const base = state.premium ? state.premium.price_rub : 21;
      const discount = state.premium ? state.premium.discount_pct || 0 : 0;
      const full = base * months;
      const effective = discount ? Math.floor((full * (100 - discount)) / 100) : full;
      return { full, effective, discount };
    }

    function planCard(state, plan) {
      const { full, effective, discount } = planPrice(state, plan.months);
      const active = state.premiumMonths === plan.months;
      const isYear = plan.months === 12;
      const forever = plan.months >= FOREVER_MONTHS;
      const badge = forever ? "Один раз — навсегда" : isYear ? "Выгоднее всего" : "";
      const monthly =
        !forever && plan.months > 1
          ? `<span class="plan-card__monthly">${Math.round(effective / plan.months)} ₽/мес</span>`
          : forever
            ? '<span class="plan-card__monthly">больше никогда не платить</span>'
            : "";
      return `
        <button class="plan-card${active ? " is-active" : ""}${isYear ? " plan-card--best" : ""}${forever ? " plan-card--forever" : ""}" data-action="premium-plan" data-months="${plan.months}">
          ${badge ? `<span class="plan-card__badge">${badge}</span>` : ""}
          <span class="plan-card__label">${plan.label}</span>
          <span class="plan-card__price">${effective} ₽${discount ? ` <s>${full} ₽</s>` : ""}</span>
          ${monthly}
        </button>
      `;
    }

    // Бесплатные 3 дня без карты — самый короткий путь к первой оплате
    function trialBanner(state) {
      if (!state.profile || !state.profile.trial_available) return "";
      return `
        <div class="trial-banner">
          <div class="trial-banner__title">🎁 ${(state.premium && state.premium.trial_days) || 7} дней Premium бесплатно</div>
          <div class="trial-banner__sub">Без карты и без автосписаний — просто попробуйте</div>
          <button class="btn btn--primary btn--block" style="margin-top:12px" data-action="start-trial">
            Забрать 3 дня
          </button>
        </div>
      `;
    }

    function renderPremium(state) {
      const isActive = state.premium && state.premium.active;
      const { effective } = planPrice(state, state.premiumMonths);

      const perks = PERKS.map(
        ([ic, label, desc]) => `
          <div class="perk-row">
            <span class="perk-row__icon">${icon(ic)}</span>
            <span class="perk-row__text">
              <span class="perk-row__title">${label}</span>
              <span class="perk-row__desc">${desc}</span>
            </span>
          </div>
        `
      ).join("");

      return `
        <div class="page-head" data-role="page-head">
          <button class="icon-btn" data-action="back" aria-label="Назад">${icon("back")}</button>
          <span>Infinity Music Premium</span>
        </div>

        <div class="premium-hero">
          <div class="premium-hero__icon">${icon("crown")}</div>
          <div class="premium-hero__title">${isActive ? "Premium активен" : "Больше музыки с Premium"}</div>
          ${isActive ? '<div class="premium-hero__sub">Продлите заранее — дни суммируются</div>' : ""}
        </div>

        ${trialBanner(state)}

        <div class="rec-section-label">Что даёт Premium</div>
        <div class="card card--flat">${perks}</div>

        <div class="rec-section-label">Тарифы</div>
        <div class="plan-grid">
          ${PLANS.map((p) => planCard(state, p)).join("")}
        </div>

        <button class="btn btn--primary btn--block" data-action="pay-premium" style="margin-top:16px">
          ${isActive ? "Продлить" : "Оформить"} за ${effective} ₽
        </button>
        <p class="page-hint" style="text-align:center">Оплата картой, СБП или SberPay через ЮKassa. Подписка активируется сразу после оплаты.</p>
        <p class="page-hint" style="text-align:center">
          Оформляя, вы соглашаетесь с
          <a href="#" data-action="open-doc" data-doc="offer">офертой</a> и автосписанием 49 ₽/мес.
          Отключить автопродление можно в настройках.
        </p>
      `;
    }
    return { FOREVER_MONTHS, renderPremium };
  })();

  __m["screens/contests.js"] = (function () {
    const { icon } = __m["components/icons.js"];
    const { escapeHtml } = __m["components/trackRow.js"];
    // Конкурсы (SPEC-2.0 §28): условия, участие, итоги.
    // Все условия проверяет сервер — экран только показывает их состояние.

    function prizeLabel(contest) {
      if (contest.prize_days === 0) return "Premium навсегда";
      return `${contest.prize_days} дней Premium`;
    }

    function endsLabel(contest) {
      const date = new Date(contest.ends_at);
      if (Number.isNaN(date.getTime())) return "";
      return date.toLocaleDateString("ru-RU", { day: "numeric", month: "long" });
    }

    function condition(done, text) {
      return `
        <div class="contest-cond${done ? " is-done" : ""}">
          <span class="contest-cond__mark">${icon(done ? "check" : "plus")}</span>
          <span class="contest-cond__text">${text}</span>
        </div>
      `;
    }

    function conditions(contest) {
      const rows = [];
      if (contest.channel_url) {
        rows.push(condition(contest.is_subscribed, "Подписаться на наш канал"));
      }
      if (contest.required_referrals > 0) {
        rows.push(
          condition(
            contest.referrals >= contest.required_referrals,
            `Пригласить друзей — ${contest.referrals} из ${contest.required_referrals}`
          )
        );
      }
      return rows.join("");
    }

    function actionButton(contest) {
      if (contest.joined) {
        return `<div class="contest-joined">${icon("check")} Вы участвуете</div>`;
      }
      if (!contest.is_subscribed && contest.channel_url) {
        return `
          <a class="contest-btn" href="${contest.channel_url}" target="_blank" rel="noopener">
            Подписаться на канал
          </a>
          <button class="contest-btn contest-btn--ghost" data-action="contest-join" data-id="${contest.id}">
            Я подписался
          </button>
        `;
      }
      const blocked = contest.referrals < contest.required_referrals;
      return `
        <button class="contest-btn" data-action="${blocked ? "open-referral" : "contest-join"}" data-id="${contest.id}">
          ${blocked ? "Пригласить друзей" : "Участвовать"}
        </button>
      `;
    }

    function contestCard(contest) {
      return `
        <div class="contest-card">
          <div class="contest-card__prize">${icon("gift")} ${prizeLabel(contest)}</div>
          <h2 class="contest-card__title">${escapeHtml(contest.title)}</h2>
          <div class="contest-card__meta">
            Итоги ${endsLabel(contest)} · участников: ${contest.participants}
          </div>
          ${contest.description ? `<p class="contest-card__text">${escapeHtml(contest.description)}</p>` : ""}
          <div class="contest-conds">${conditions(contest)}</div>
          <div class="contest-card__actions">${actionButton(contest)}</div>
          <div class="contest-card__note">
            Победителя выбираем случайным образом среди тех, кто выполнил условия.
            Premium активируется автоматически.
          </div>
        </div>
      `;
    }

    function renderContests(state) {
      const contests = state.contests;

      if (contests === null || contests === undefined) {
        return `<div class="screen-pad"><div class="empty">Загружаем конкурсы…</div></div>`;
      }

      if (!contests.length) {
        return `
          <div class="screen-pad">
            <div class="empty">
              <div class="empty__title">Сейчас конкурсов нет</div>
              <div class="empty__sub">Загляните позже — разыгрываем Premium регулярно</div>
            </div>
          </div>
        `;
      }

      return `<div class="screen-pad contest-list">${contests.map(contestCard).join("")}</div>`;
    }
    return { renderContests };
  })();

  __m["equalizer.js"] = (function () {
    const { audio } = __m["state.js"];
    // Эквалайзер (скрины VK в копи/): 7 полос Web Audio поверх <audio> плеера.
    // Граф строится лениво при первом включении — если AudioContext недоступен
    // (старый webview), плеер продолжает играть без эквалайзера.


    const EQ_FREQS = [50, 100, 200, 400, 1000, 2500, 15000];
    const EQ_MIN_DB = -12;
    const EQ_MAX_DB = 12;

    const EQ_KEY = "tgmusic-equalizer";

    // Пресеты как в VK: имя → усиление (дБ) по 7 полосам
    const EQ_PRESETS = [
      { id: "custom", label: "Пользовательская", gains: null },
      { id: "flat", label: "Ровно", gains: [0, 0, 0, 0, 0, 0, 0] },
      { id: "acoustic", label: "Акустика", gains: [4, 3, 1, 0, 1, 2, 3] },
      { id: "bass", label: "Больше басов", gains: [6, 5, 3, 0, 0, 0, 0] },
      { id: "bassplus", label: "Больше басов +", gains: [9, 7, 4, 0, 0, 0, 0] },
      { id: "lessbass", label: "Меньше басов", gains: [-6, -4, -2, 0, 0, 0, 0] },
      { id: "dance", label: "Танцевальная", gains: [5, 4, 2, 0, 2, 3, 4] },
      { id: "deep", label: "Глубокое звучание", gains: [5, 4, 1, 0, -1, 1, 2] },
      { id: "electronic", label: "Электроника", gains: [5, 3, 0, -1, 2, 4, 5] },
      { id: "hiphop", label: "Хип-хоп", gains: [6, 5, 2, 0, 1, 2, 3] },
      { id: "jazz", label: "Джаз", gains: [3, 2, 0, 1, 2, 3, 3] },
      { id: "classical", label: "Классика", gains: [4, 3, 0, 0, 0, 2, 4] },
      { id: "pop", label: "Поп", gains: [1, 2, 3, 4, 2, 0, -1] },
      { id: "rnb", label: "RnB", gains: [5, 4, 1, 0, 2, 3, 2] },
      { id: "rock", label: "Рок", gains: [4, 3, 1, 0, 2, 3, 4] },
      { id: "vocal", label: "Вокал", gains: [-2, -1, 1, 4, 4, 2, 0] },
      { id: "speech", label: "Речь", gains: [-3, -2, 2, 5, 4, 1, -2] },
      { id: "loud", label: "Больше громкости", gains: [3, 3, 3, 3, 3, 3, 3] },
      { id: "treble", label: "Больше высоких", gains: [0, 0, 0, 0, 2, 4, 6] },
      { id: "lesstreble", label: "Меньше высоких", gains: [0, 0, 0, 0, -2, -4, -6] },
      { id: "headphones", label: "Наушники", gains: [4, 3, 1, 0, 1, 3, 4] },
    ];

    function getEqSettings() {
      const fallback = { enabled: false, preset: "flat", custom: [0, 0, 0, 0, 0, 0, 0] };
      try {
        const saved = JSON.parse(localStorage.getItem(EQ_KEY) || "{}");
        return { ...fallback, ...saved };
      } catch {
        return fallback;
      }
    }

    function saveEqSettings(settings) {
      try {
        localStorage.setItem(EQ_KEY, JSON.stringify(settings));
      } catch {
        // приватный режим — эквалайзер поживёт до перезапуска
      }
    }

    function currentGains(settings = getEqSettings()) {
      if (settings.preset === "custom") return settings.custom;
      const preset = EQ_PRESETS.find((p) => p.id === settings.preset);
      return (preset && preset.gains) || [0, 0, 0, 0, 0, 0, 0];
    }

    let ctx = null;
    let filters = [];
    let graphFailed = false;

    function ensureGraph() {
      if (ctx) return true;
      if (graphFailed) return false;
      try {
        const AudioCtx = window.AudioContext || window.webkitAudioContext;
        ctx = new AudioCtx();
        const source = ctx.createMediaElementSource(audio);
        filters = EQ_FREQS.map((freq, i) => {
          const filter = ctx.createBiquadFilter();
          filter.type = i === 0 ? "lowshelf" : i === EQ_FREQS.length - 1 ? "highshelf" : "peaking";
          filter.frequency.value = freq;
          filter.Q.value = 1;
          filter.gain.value = 0;
          return filter;
        });
        [source, ...filters].reduce((from, to) => {
          from.connect(to);
          return to;
        }).connect(ctx.destination);
        return true;
      } catch {
        graphFailed = true;
        ctx = null;
        return false;
      }
    }

    function eqSupported() {
      return !graphFailed && Boolean(window.AudioContext || window.webkitAudioContext);
    }

    // Применить текущие настройки к графу. Выключен — все полосы в 0 (прозрачно).
    function applyEqualizer() {
      const settings = getEqSettings();
      if (!settings.enabled && !ctx) return; // граф не строим, пока EQ не включали
      if (!ensureGraph()) return;
      if (ctx.state === "suspended") ctx.resume().catch(() => {});
      const gains = settings.enabled ? currentGains(settings) : [0, 0, 0, 0, 0, 0, 0];
      filters.forEach((filter, i) => {
        filter.gain.value = gains[i] || 0;
      });
    }

    // Автоплей-политики: контекст оживает на реальном воспроизведении
    audio.addEventListener("play", applyEqualizer);
    return { EQ_FREQS, EQ_MIN_DB, EQ_MAX_DB, EQ_PRESETS, getEqSettings, saveEqSettings, currentGains, eqSupported, applyEqualizer };
  })();

  __m["screens/equalizer.js"] = (function () {
    const { icon } = __m["components/icons.js"];
    const { EQ_FREQS, EQ_MAX_DB, EQ_MIN_DB, EQ_PRESETS, currentGains, eqSupported, getEqSettings } = __m["equalizer.js"];
    // Эквалайзер по скринам VK (копи/): тумблер, 7 вертикальных полос, пресеты.

    function freqLabel(freq) {
      return freq >= 1000 ? `${freq / 1000} кГц`.replace(".", ",") : `${freq} Гц`;
    }

    function renderBands(settings) {
      const gains = currentGains(settings);
      const bands = EQ_FREQS.map(
        (freq, i) => `
          <div class="eq-band">
            <div class="eq-band__slider">
              <input type="range" min="${EQ_MIN_DB}" max="${EQ_MAX_DB}" step="1"
                value="${gains[i] || 0}" data-role="eq-band" data-band="${i}"
                ${settings.enabled ? "" : "disabled"} />
            </div>
            <span class="eq-band__label">${freqLabel(freq)}</span>
          </div>
        `
      ).join("");
      return `<div class="eq-bands${settings.enabled ? "" : " is-disabled"}">${bands}</div>`;
    }

    function renderPresets(settings) {
      const rows = EQ_PRESETS.map(
        (preset) => `
          <button class="sheet-item" data-action="eq-preset" data-value="${preset.id}">
            <span style="flex:1;text-align:left">${preset.label}</span>
            ${settings.preset === preset.id ? icon("check") : ""}
          </button>
        `
      ).join("");
      return `<div class="card card--rows">${rows}</div>`;
    }

    function renderEqualizer() {
      const settings = getEqSettings();
      if (!eqSupported()) {
        return `
          <div class="page-head" data-role="page-head">
            <button class="icon-btn" data-action="back" aria-label="Назад">${icon("back")}</button>
            <span>Эквалайзер</span>
          </div>
          <div class="empty-state">Эквалайзер не поддерживается этим устройством.</div>
        `;
      }
      return `
        <div class="page-head" data-role="page-head">
          <button class="icon-btn" data-action="back" aria-label="Назад">${icon("back")}</button>
          <span>Эквалайзер</span>
        </div>
        <div class="settings-row" style="width:100%">
          <div class="settings-row__label">Включить эквалайзер</div>
          <button class="switch${settings.enabled ? " is-on" : ""}" data-action="eq-toggle" aria-label="Эквалайзер"></button>
        </div>
        ${renderBands(settings)}
        ${renderPresets(settings)}
      `;
    }
    return { renderEqualizer };
  })();

  __m["screens/interface.js"] = (function () {
    const { icon } = __m["components/icons.js"];
    const { getUiSettings } = __m["prefs.js"];
    // «Интерфейс» по скрину VK (копи/ photo_19): акцентный цвет + тактильная
    // обратная связь. Тема одна — тёмная (решение владельца), переключателя нет.

    const ACCENTS = [
      { id: "gold", label: "Золотой", color: "#f5a623" },
      { id: "pink", label: "Розовый", color: "#ef3f7f" },
      { id: "green", label: "Люминесцентный зелёный", color: "#32d74b" },
      { id: "azure", label: "Лазурный", color: "#32ade6" },
      { id: "blue", label: "Синий", color: "#3b7bfe" },
    ];

    function renderInterface() {
      const ui = getUiSettings();
      const rows = ACCENTS.map(
        (accent) => `
          <button class="sheet-item" data-action="set-accent" data-value="${accent.id}">
            <span style="flex:1;text-align:left;color:${accent.color};font-weight:700">${accent.label}</span>
            ${ui.accent === accent.id ? icon("check") : ""}
          </button>
        `
      ).join("");

      return `
        <div class="page-head" data-role="page-head">
          <button class="icon-btn" data-action="back" aria-label="Назад">${icon("back")}</button>
          <span>Интерфейс</span>
        </div>
        <div class="rec-section-label">Акцентный цвет</div>
        <div class="hint-text">С любимым цветом интерфейс удобнее и краше</div>
        <div class="card card--rows">${rows}</div>
        <div class="settings-row" style="width:100%;margin-top:14px">
          <div class="settings-row__label">
            <div>
              Тактильная обратная связь
              <div class="hint-text">Почувствуйте работу приложения кончиками пальцев</div>
            </div>
          </div>
          <button class="switch${ui.haptic ? " is-on" : ""}" data-action="toggle-haptic" aria-label="Тактильная обратная связь"></button>
        </div>
      `;
    }
    return { ACCENTS, renderInterface };
  })();

  __m["screens/storage.js"] = (function () {
    const { icon } = __m["components/icons.js"];
    const { offlineTracks } = __m["offline.js"];
    // «Память устройства» по скрину VK (копи/ photo_15): очистка скачанных треков.
    // Скачанные живут в Cache API + индекс в localStorage (offline.js).

    function renderStorage() {
      const count = offlineTracks().length;
      return `
        <div class="page-head" data-role="page-head">
          <button class="icon-btn" data-action="back" aria-label="Назад">${icon("back")}</button>
          <span>Память устройства</span>
        </div>
        <div class="rec-section-label">Память устройства</div>
        <div class="settings-row" style="width:100%">
          <div class="settings-row__label">
            <div>
              Удалить загруженные треки
              <div class="hint-text">Удалите всю скачанную музыку — раздел «Скачанные» будет очищен</div>
            </div>
          </div>
          <span class="hint-text">${count}</span>
        </div>
        <button class="btn btn--ghost btn--block" style="margin-top:12px${count ? "" : ";opacity:.5"}"
          data-action="clear-offline" ${count ? "" : "disabled"}>
          🗑 Удалить скачанные треки
        </button>
      `;
    }
    return { renderStorage };
  })();

  __m["screens/transfer.js"] = (function () {
    const { icon } = __m["components/icons.js"];
    const { escapeHtml } = __m["components/trackRow.js"];
    // «Перенос из других сервисов» по скрину VK (копи/ photo_16): выбор сервиса,
    // поле для ссылки/списка, объяснение как это работает.

    const SERVICES = [
      {
        id: "spotify",
        label: "Spotify",
        hint: "Ссылка на плейлист",
        tone: "spotify",
        prompt: "Скопируйте ссылку на свой плейлист в Spotify",
        help: "Откройте плейлист в Spotify → «…» → «Поделиться» → «Копировать ссылку».",
        warn: "Плейлист должен быть публичным — проверьте настройки приватности.",
      },
      {
        id: "yandex",
        label: "Яндекс",
        hint: "Ссылка на плейлист",
        tone: "yandex",
        prompt: "Скопируйте ссылку на свой плейлист в Яндекс Музыке",
        help: "Откройте плейлист в Яндекс Музыке → «Поделиться» → «Скопировать ссылку».",
        warn: "Плейлист должен быть публичным — проверьте настройки приватности.",
      },
      {
        id: "vk",
        label: "ВКонтакте",
        hint: "Список текстом",
        tone: "vk",
        prompt: "Вставьте список треков — по строке на трек",
        help: "ВКонтакте не отдаёт плейлисты без входа. Скопируйте названия треков и вставьте строками «Артист — Название».",
        warn: "",
      },
      {
        id: "soundcloud",
        label: "SoundCloud",
        hint: "Профиль, трек или сет",
        tone: "sc",
        prompt: "Скопируйте ссылку на трек, профиль или сет SoundCloud",
        help: "SoundCloud скачивается напрямую — принимаем ссылку на трек, профиль, лайки или сет.",
        warn: "",
      },
    ];

    function renderTransfer(state) {
      const cards = SERVICES.map(
        (service) => `
          <button class="transfer-card transfer-card--${service.tone}${state.transferService === service.id ? " is-active" : ""}"
            data-action="transfer-service" data-value="${service.id}">
            <span class="transfer-card__logo">${service.label[0]}</span>
            <span class="transfer-card__label">${service.label}</span>
            <span class="transfer-card__hint">${service.hint}</span>
          </button>
        `
      ).join("");

      const active = SERVICES.find((s) => s.id === state.transferService) || SERVICES[0];
      const isVk = active.id === "vk";
      const placeholder = isVk
        ? "Kizaru — Fendi&#10;Big Baby Tape — Gimme the Loot"
        : "https://…";

      return `
        <div class="page-head" data-role="page-head">
          <button class="icon-btn" data-action="back" aria-label="Назад">${icon("back")}</button>
          <span>Перенос музыки</span>
        </div>

        <div class="transfer-hero">
          <div class="transfer-hero__title">Перенесите плейлисты из других сервисов</div>
          <div class="transfer-hero__sub">Слушайте любимые треки в Infinity Music</div>
        </div>

        <div class="rec-section-label">Откуда перенести?</div>
        <div class="transfer-grid">${cards}</div>

        <div class="transfer-prompt">${active.prompt}</div>
        <textarea class="transfer-input" data-role="transfer-input" rows="${isVk ? 4 : 2}"
          placeholder="${placeholder}">${escapeHtml(state.transferSource || "")}</textarea>
        <div class="hint-text">${active.help}</div>
        ${active.warn ? `<div class="transfer-warn">${active.warn}</div>` : ""}

        <button class="btn btn--primary btn--block" style="margin-top:14px" data-action="transfer-start">
          ${state.transferStatus === "loading" ? "Переношу…" : "Перенести"}
        </button>

        ${state.transferResult ? `<div class="card card--flat transfer-result">${state.transferResult}</div>` : ""}

        <div class="rec-section-label">Как это работает</div>
        <div class="card card--rows transfer-steps">
          <div class="settings-row"><div class="settings-row__label">1. Находим ваши треки в нашей базе — они появляются сразу</div></div>
          <div class="settings-row"><div class="settings-row__label">2. Чего нет — загружаем из открытых источников</div></div>
          <div class="settings-row"><div class="settings-row__label">3. Пришлём отчёт в чат, когда закончим</div></div>
        </div>
      `;
    }
    return { renderTransfer };
  })();

  __m["screens/upload.js"] = (function () {
    const { icon } = __m["components/icons.js"];
    const { escapeHtml } = __m["components/trackRow.js"];
    // Загрузка своего трека из Mini App (запрос владельца: грузить и через мини-апку).
    // Исполнитель обязателен — иначе трек уйдёт как «Неизвестный».

    function renderUpload(state) {
      const u = state.upload || {};
      const fileName = u.fileName ? escapeHtml(u.fileName) : "";
      const busy = u.status === "loading";

      return `
        <div class="page-head" data-role="page-head">
          <button class="icon-btn" data-action="back" aria-label="Назад">${icon("back")}</button>
          <span>Загрузить трек</span>
        </div>

        <div class="rec-section-label">Аудиофайл</div>
        <label class="upload-drop">
          <input type="file" accept="audio/*" data-role="upload-file" hidden />
          <span class="upload-drop__icon">${icon("import")}</span>
          <span class="upload-drop__text">${fileName || "Выберите аудиофайл (MP3, M4A…)"}</span>
        </label>

        <div class="rec-section-label">Название</div>
        <input class="transfer-input" data-role="upload-title" placeholder="Название трека"
          value="${escapeHtml(u.title || "")}" />

        <div class="rec-section-label">Исполнитель <span class="req-mark">обязательно</span></div>
        <input class="transfer-input" data-role="upload-artist" placeholder="Имя исполнителя"
          value="${escapeHtml(u.artist || "")}" />

        <button class="btn btn--primary btn--block" style="margin-top:16px"
          data-action="upload-submit" ${busy ? "disabled" : ""}>
          ${busy ? "Загружаю…" : "Добавить в библиотеку"}
        </button>

        ${u.result ? `<div class="card card--flat transfer-result">${u.result}</div>` : ""}

        <div class="hint-text" style="margin-top:14px">
          Трек попадёт в вашу библиотеку и общий поиск. Указывайте исполнителя —
          без него трек будет «Неизвестным» и потеряется в базе.
        </div>
      `;
    }
    return { renderUpload };
  })();

  __m["screens/onboarding.js"] = (function () {
    const { icon } = __m["components/icons.js"];
    const { escapeHtml } = __m["components/trackRow.js"];
    const { isFavoriteArtist } = __m["prefs.js"];
    // Онбординг при первом входе (запрос владельца): знакомим с приложением,
    // спрашиваем любимых исполнителей (для рекомендаций), предлагаем импорт музыки.

    function renderWelcome() {
      return `
        <div class="onb-hero">
          <div class="onb-hero__logo">🎧</div>
          <div class="onb-hero__title">Добро пожаловать в Infinity Music</div>
          <div class="onb-hero__sub">Вся музыка в Телеграме: миксы под настроение, поиск, плейлисты, эквалайзер и офлайн</div>
        </div>
        <div class="onb-points">
          <div class="onb-point">${icon("play")}<span>Слушайте бесконечные миксы под ваш вкус</span></div>
          <div class="onb-point">${icon("import")}<span>Переносите плейлисты из Spotify, Яндекса и ВК</span></div>
          <div class="onb-point">${icon("gift")}<span>Зовите друзей — получайте Premium бесплатно</span></div>
        </div>
        <button class="btn btn--primary btn--block" data-action="onb-next">Начать</button>
      `;
    }

    function renderArtists(state) {
      const artists = state.onbArtists || [];
      if (!artists.length) {
        // Нет данных об исполнителях (пустая база) — пропускаем шаг
        return `
          <div class="onb-step-head">Почти готово</div>
          <div class="onb-step-sub">Отметьте любимых исполнителей позже в настройках — микс станет точнее.</div>
          <button class="btn btn--primary btn--block" data-action="onb-next">Далее</button>
        `;
      }
      const chips = artists
        .map(
          (a) => `
            <button class="onb-chip${isFavoriteArtist(a.name) ? " is-active" : ""}"
              data-action="onb-artist" data-name="${escapeHtml(a.name)}">
              ${escapeHtml(a.name)}
            </button>
          `
        )
        .join("");
      return `
        <div class="onb-step-head">Какие артисты вам нравятся?</div>
        <div class="onb-step-sub">Выберите несколько — подстроим рекомендации под вас</div>
        <div class="onb-chips">${chips}</div>
        <button class="btn btn--primary btn--block" data-action="onb-next">Далее</button>
      `;
    }

    function renderImport() {
      return `
        <div class="onb-hero">
          <div class="onb-hero__logo">📥</div>
          <div class="onb-hero__title">Перенесите свою музыку</div>
          <div class="onb-hero__sub">Забыли любимые треки в другом сервисе? Перенесём их в Infinity Music за минуту.</div>
        </div>
        <button class="btn btn--primary btn--block" data-action="onb-import">Перенести из Spotify, Яндекса, ВК</button>
        <button class="btn btn--ghost btn--block" style="margin-top:10px" data-action="onb-finish">Позже, начать слушать</button>
      `;
    }

    const STEPS = [renderWelcome, renderArtists, renderImport];

    function renderOnboarding(state) {
      const step = state.onbStep || 0;
      const dots = STEPS.map(
        (_, i) => `<span class="onb-dot${i === step ? " is-active" : ""}"></span>`
      ).join("");
      return `
        <div class="onboarding">
          <div class="onb-dots">${dots}</div>
          <div class="onb-body">${STEPS[step](state)}</div>
        </div>
      `;
    }
    return { renderOnboarding };
  })();

  __m["screens/subgate.js"] = (function () {
    const { icon } = __m["components/icons.js"];
    const { escapeHtml } = __m["components/trackRow.js"];
    // Гейт обязательной подписки (блок B): показывается поверх всего, если пользователь
    // не подписан на обязательные каналы и у него нет Premium. Кнопки каналов + «Я
    // подписался» (перепроверка) + «Убрать подписки» (Premium снимает ОП).
    function renderSubGate(state) {
      const gate = state.subGate;
      if (!gate) return "";
      const channels = gate.channels
        .filter((c) => c.url)
        .map(
          (c) => `
          <a class="btn btn--primary sub-gate__channel${c.subscribed ? " is-done" : ""}"
             href="${escapeHtml(c.url)}" target="_blank" rel="noopener"
             data-action="sub-click" data-cid="${c.id}">
            ${c.subscribed ? icon("check") : icon("bell")} ${escapeHtml(c.label)}
          </a>`
        )
        .join("");
      return `
        <div class="sub-gate">
          <div class="sub-gate__icon">${icon("note")}</div>
          <h1 class="sub-gate__title">Подпишитесь, чтобы слушать</h1>
          <p class="sub-gate__text">
            Infinity Music бесплатен, пока вы подписаны на наши каналы.
            Оформите Premium — и обязательные подписки больше не нужны.
          </p>
          <div class="sub-gate__channels">${channels}</div>
          <button class="btn btn--primary sub-gate__check" data-action="sub-recheck">Я подписался</button>
          <button class="btn btn--ghost" data-action="sub-premium">Убрать подписки — Premium</button>
        </div>
      `;
    }
    return { renderSubGate };
  })();

  __m["screens/paywall.js"] = (function () {
    const { icon } = __m["components/icons.js"];
    // Пэйвол Mini App (решение владельца): бот бесплатный, приложение — по подписке.
    // 7 дней бесплатно (включаются сами при первом открытии, 15.09) — этот экран видит
    // тот, у кого пробный период уже был. Текст объясняет, за что платят,
    // и честно говорит, что цена временная — деньги идут на серверы.

    const FEATURES = [
      ["🎛", "Плеер как в больших сервисах", "Очередь, эквалайзер на 7 полос, таймер сна, повтор, тексты песен"],
      ["🎧", "Миксы под настроение", "Infinity Mix собирает подборку под ваш вкус — и не крутит одно и то же"],
      ["🎤", "Карточки артистов", "Фото, жанры, топ треков, альбомы, похожие исполнители, подписка"],
      ["📚", "Библиотека и плейлисты", "Свои плейлисты, «Мои треки», сортировка, поиск по разделам"],
      ["📥", "Офлайн-режим", "Скачивайте треки в приложение и слушайте без интернета"],
      ["🚫", "Без рекламы и без обязательных подписок", "Ничто не отвлекает"],
    ];

    function renderPaywall(state) {
      const price = (state.premium && state.premium.price_rub) || 49;
      const trialAvailable = state.premium
        ? Boolean(state.premium.trial_available)
        : Boolean(state.profile && state.profile.trial_available);
      const trialDays = (state.premium && state.premium.trial_days) || 7;

      const features = FEATURES.map(
        ([emoji, title, text]) => `
          <div class="paywall-feature">
            <span class="paywall-feature__emoji">${emoji}</span>
            <span class="paywall-feature__body">
              <span class="paywall-feature__title">${title}</span>
              <span class="paywall-feature__text">${text}</span>
            </span>
          </div>
        `
      ).join("");

      const trialButton = trialAvailable
        ? `<button class="btn btn--primary paywall__cta" data-action="paywall-trial">
             ${icon("sparkles")} Попробовать бесплатно — ${trialDays} дней
           </button>`
        : "";

      return `
        <div class="paywall">
          <div class="paywall__hero">
            <div class="paywall__badge">Полная версия</div>
            <h1 class="paywall__title">Infinity Music Плеер</h1>
            <p class="paywall__lead">
              Музыка в боте — <b>бесплатно навсегда</b>. Приложение — это уже отдельный
              сервис: плеер, миксы, плейлисты, артисты и офлайн.
            </p>
          </div>

          <div class="paywall__features">${features}</div>

          <div class="paywall__price">
            <div class="paywall__price-value">${price} ₽<span>/месяц</span></div>
            <div class="paywall__price-note">
              Дешевле чашки кофе. Цена временная — пока набираем на серверы,
              потом станет дороже. Отписаться можно в любой момент.
            </div>
          </div>

          ${trialButton}
          <button class="btn ${trialAvailable ? "btn--ghost" : "btn--primary"} paywall__cta" data-action="paywall-buy">
            ${icon("premium")} Открыть за ${price} ₽
          </button>

          <p class="paywall__footer">
            Не хотите платить — просто пользуйтесь ботом: там поиск и скачивание
            музыки без ограничений.
          </p>
        </div>
      `;
    }
    return { renderPaywall };
  })();

  __m["main.js"] = (function () {
    const { trackClient } = __m["analytics.js"];
    const { addToLibrary, createPaymentLink, formatDuration, getLibrary, getLibraryIds, getAlbums, getAlbumTracks, getArtists, getArtistCard, getArtistTracks, getContests, getGenres, getGenreTracks, followArtist, unfollowArtist, getMyArtists, addTrackToPlaylist, searchAll, liveSearch, searchLiveAlbums, getLiveAlbumTracks, addLiveAlbumToLibrary, liveStreamUrl, queueLiveFetch, getInstrumentals, getLyrics, getPlaylists, getPlaylistTracks, getPopularQueries, joinContest, getPremiumStatus, getSubscriptionStatus, logChannelClick, fetchFromWeb, getProfile, getTracks, login, logSearchQuery, createPlaylist, submitLyrics, removeFromLibrary, getLanguages, resolveAudioUrl, saveLanguage, sendTrackToChat, telegramUser } = __m["api.js"];
    const { closePlayer, closeSheet, getState, goBack, mutate, navigateTo, openPlayer, openSheet, playMix, playQueueIndex, playRecommended, playVibe, playNext, playPrev, playTrack, playTrackMix, addToQueue, playNextInQueue, resetToTab, seekToFraction, setSleepTimer, showToast, subscribe, subscribeProgress, togglePlay, toggleRepeat, toggleShuffle } = __m["state.js"];
    const { renderHeader } = __m["components/header.js"];
    const { renderBottomNav } = __m["components/bottomNav.js"];
    const { renderMiniPlayer } = __m["components/miniPlayer.js"];
    const { renderPlayerScreen } = __m["components/playerScreen.js"];
    const { renderTrackSheet } = __m["components/trackSheet.js"];
    const { renderPlaylistPicker } = __m["components/playlistPicker.js"];
    const { icon } = __m["components/icons.js"];
    const { escapeHtml } = __m["components/trackRow.js"];
    const { renderHome } = __m["screens/home.js"];
    const { renderSearch, renderSearchResults } = __m["screens/search.js"];
    const { renderLibrary } = __m["screens/library.js"];
    const { renderMyTracks, renderMyTracksBody, myTracksList } = __m["screens/mytracks.js"];
    const { renderProfile } = __m["screens/profile.js"];
    const { renderSettings } = __m["screens/settings.js"];
    const { renderLanguage } = __m["screens/language.js"];
    const { getLanguage, setLanguage } = __m["i18n.js"];
    const { renderRecommendations } = __m["screens/recommendations.js"];
    const { renderRecent } = __m["screens/recent.js"];
    const { renderArtists } = __m["screens/artists.js"];
    const { renderArtistCard } = __m["screens/artistcard.js"];
    const { renderMyArtists } = __m["screens/myartists.js"];
    const { renderDocs } = __m["screens/docs.js"];
    const { renderAchievements } = __m["screens/achievements.js"];
    const { renderLyrics } = __m["screens/lyrics.js"];
    const { renderDownloads } = __m["screens/downloads.js"];
    const { renderPlaylists } = __m["screens/playlists.js"];
    const { renderAlbums } = __m["screens/albums.js"];
    const { renderCollection } = __m["screens/collection.js"];
    const { renderReferral } = __m["screens/referral.js"];
    const { renderPremium } = __m["screens/premium.js"];
    const { renderContests } = __m["screens/contests.js"];
    const { renderEqualizer } = __m["screens/equalizer.js"];
    const { renderInterface } = __m["screens/interface.js"];
    const { renderStorage } = __m["screens/storage.js"];
    const { renderTransfer } = __m["screens/transfer.js"];
    const { renderUpload } = __m["screens/upload.js"];
    const { renderOnboarding } = __m["screens/onboarding.js"];
    const { renderSubGate } = __m["screens/subgate.js"];
    const { renderPaywall } = __m["screens/paywall.js"];
    const { isOffline, offlineSupported, saveOffline, removeOffline, offlineTracks } = __m["offline.js"];
    const { getRecentTracks, saveRecSettings, clearRecSettings, pushRecentSearch, clearRecentSearches, toggleFavoriteArtist, applyAccent, getUiSettings, saveUiSettings, isOnboarded, isOnboardedCloud, setOnboarded } = __m["prefs.js"];
    const { applyEqualizer, currentGains, getEqSettings, saveEqSettings } = __m["equalizer.js"];
    const { getTrackById, getProfileTop, getReferralTop, startPremiumTrial, startTransfer, uploadTrack } = __m["api.js"];
    const root = document.getElementById("app");
    const tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;

    // Зеркалит settings.bot_username: сюда ведут «Поделиться» и «Открыть бота».
    // При смене бота править и здесь, и в app/config.py — иначе ссылки уводят на старого.
    const BOT_USERNAME = "muz_damn_bot";

    // Страницу открыли в обычном браузере, а не из Telegram: скрипт telegram.org
    // создаёт window.Telegram.WebApp где угодно, но initData непустой только внутри
    // клиента. Войти нечем, и приложению здесь делать нечего — поэтому оно вообще не
    // трогает DOM: в #app из index.html лежит описание сервиса со ссылками на бота,
    // поддержку и страницу «О сервисе». Раньше первый же render() затирал его
    // экраном «Откройте приложение из Telegram», и посетитель упирался в тупик без
    // единой ссылки — заодно это возвращало профиль «пустая страница под брендом
    // Telegram», из-за которого Safari ругался на домен.
    const OUTSIDE_TELEGRAM = (() => {
      try {
        // Dev-вход по токену из localStorage — это отладка в браузере, она должна жить
        if (localStorage.getItem("tgmusic-dev-token")) return false;
      } catch {
        // приватный режим не отдаёт localStorage — считаем, что токена нет
      }
      return !(tg && tg.initData);
    })();

    if (tg) {
      tg.ready();
      tg.expand();
      // «Сворачивать, а не закрывать»: подтверждение на закрытие спасает от случайного
      // креста (музыка живёт при сворачивании ⌄, но умирает при закрытии), а отключение
      // вертикальных свайпов Telegram даёт работать нашим свайпам внутри приложения.
      try {
        if (typeof tg.enableClosingConfirmation === "function") tg.enableClosingConfirmation();
        if (typeof tg.disableVerticalSwipes === "function") tg.disableVerticalSwipes();
      } catch {
        // старый клиент Telegram — просто без этих плюшек
      }
    }

    applyAccent(); // сохранённый акцентный цвет — до первого рендера

    function hapticTap() {
      if (!getUiSettings().haptic) return;
      if (tg && tg.HapticFeedback && tg.HapticFeedback.impactOccurred) {
        tg.HapticFeedback.impactOccurred("light");
      }
    }

    const SCREENS = {
      home: renderHome,
      search: renderSearch,
      library: renderLibrary,
      mytracks: renderMyTracks,
      profile: renderProfile,
      settings: renderSettings,
      language: renderLanguage,
      recommendations: renderRecommendations,
      equalizer: renderEqualizer,
      interface: renderInterface,
      storage: renderStorage,
      transfer: renderTransfer,
      upload: renderUpload,
      recent: renderRecent,
      artists: renderArtists,
      artist: renderArtistCard,
      myartists: renderMyArtists,
      docs: renderDocs,
      achievements: renderAchievements,
      lyrics: renderLyrics,
      downloads: renderDownloads,
      playlists: renderPlaylists,
      albums: renderAlbums,
      collection: renderCollection,
      referral: renderReferral,
      premium: renderPremium,
      contests: renderContests,
    };

    const TAB_SCREENS = new Set(["home", "search", "library"]);

    // ---------- Рендер ----------

    function renderBootScreen(state) {
      if (state.bootStatus === "loading") {
        return '<div class="boot-screen"><div class="boot-spinner"></div><p>Загружаю музыку…</p></div>';
      }
      return `
        <div class="boot-screen">
          <p class="boot-error">${state.bootError}</p>
          <button class="btn btn--primary" data-action="retry-boot">Повторить</button>
        </div>
      `;
    }

    // Рендер батчится в один кадр: серия mutate() подряд (загрузка данных, тосты,
    // смена трека) не перерисовывает DOM несколько раз за тик.
    let renderScheduled = false;
    let lastHtml = "";

    function scheduleRender() {
      if (renderScheduled) return;
      renderScheduled = true;
      // Микрозадача, а не requestAnimationFrame: rAF не срабатывает в свёрнутом
      // Mini App, и экран застывал бы на «Загружаю музыку…»
      queueMicrotask(() => {
        renderScheduled = false;
        render();
      });
    }

    function render() {
      if (OUTSIDE_TELEGRAM) return; // статичная страница из index.html остаётся как есть
      const state = getState();

      if (state.bootStatus !== "ready") {
        root.innerHTML = renderBootScreen(state);
        lastHtml = "";
        return;
      }

      // Онбординг первого входа — поверх всего, без навигации и хедера
      if (state.onbActive) {
        const onbHtml = renderOnboarding(state);
        if (onbHtml !== lastHtml) {
          lastHtml = onbHtml;
          root.innerHTML = onbHtml;
        }
        return;
      }

      // Гейт обязательной подписки — поверх всего (блок B). Premium снимает.
      if (state.subGate) {
        const gateHtml = renderSubGate(state);
        if (gateHtml !== lastHtml) {
          lastHtml = gateHtml;
          root.innerHTML = gateHtml;
        }
        return;
      }

      // Пэйвол: приложение — по подписке (бот остаётся бесплатным). Показываем
      // только когда статус Premium уже известен, чтобы не мигать на загрузке.
      if (state.premium && !state.premium.active) {
        const paywallHtml = renderPaywall(state);
        if (paywallHtml !== lastHtml) {
          // Показ пэйвола — один раз при переходе на него, не на каждую перерисовку
          if (!lastHtml || !lastHtml.includes('class="paywall"')) trackClient("paywall_view");
          lastHtml = paywallHtml;
          root.innerHTML = paywallHtml;
        }
        return;
      }

      const showNav = TAB_SCREENS.has(state.screen);
      const screenRenderer = SCREENS[state.screen] || renderHome;
      root.classList.toggle("is-playing", Boolean(state.currentTrack) && !state.playerOpen);
      root.classList.toggle("has-nav", showNav);

      const focused = document.activeElement;
      const focusedRole = focused && focused.dataset ? focused.dataset.role : null;
      const keepFocus = focusedRole === "search-input" || focusedRole === "mytracks-search";
      const caret = keepFocus ? focused.selectionStart : null;

      // Мини-плеер и нижняя навигация живут в одном фиксированном доке —
      // не перекрывают друг друга и контент (ТЗ §2).
      const html = `
        ${renderHeader(state)}
        <main class="screen">${screenRenderer(state)}</main>
        <div class="bottom-dock">
          ${renderMiniPlayer(state)}
          ${showNav ? renderBottomNav(state.screen) : ""}
        </div>
        ${renderPlayerScreen(state)}
        ${renderTrackSheet(state)}
        ${renderPlaylistPicker(state)}
        ${state.toast ? `<div class="toast">${escapeHtml(state.toast)}</div>` : ""}
      `;

      if (html === lastHtml) return; // состояние изменилось, разметка — нет: DOM не трогаем
      lastHtml = html;
      // Черновики полей, о которых state не знает (исполнитель в загрузке, список для
      // переноса, текст песни, имя плейлиста). innerHTML пересоздаёт узлы, и любой
      // тост, смена трека или фоновая догрузка стирали набранное. Возвращаем значение
      // в поле той же роли, если исходное значение поля при этом не поменялось.
      const drafts = [];
      root.querySelectorAll("input[data-role], textarea[data-role]").forEach((el) => {
        if (el.type === "file" || el.type === "range") return;
        if (el.value !== el.defaultValue) drafts.push([el.dataset.role, el.defaultValue, el.value]);
      });
      root.innerHTML = html;
      for (const [role, initial, value] of drafts) {
        const el = root.querySelector(`[data-role="${role}"]`);
        if (el && el.defaultValue === initial) el.value = value;
      }

      if (keepFocus) {
        const input = root.querySelector(`[data-role="${focusedRole}"]`);
        if (input) {
          input.focus();
          input.setSelectionRange(caret, caret);
        }
      }
    }

    subscribe(scheduleRender);

    // Пока палец ведёт перемотку — прогресс из аудио игнорируем, иначе бегунок
    // дёргается назад под пальцем.
    let isSeeking = false;

    // Прогресс — мимо полного рендера: правим только стили/текст существующих узлов.
    subscribeProgress((current, duration) => {
      if (!duration || isSeeking) return;
      const fraction = Math.min(1, current / duration);
      const fill = document.getElementById("player-progress-fill");
      const thumb = document.getElementById("player-progress-thumb");
      const time = document.getElementById("player-time-current");
      const miniFill = document.getElementById("mini-progress-fill");
      if (fill) fill.style.width = `${fraction * 100}%`;
      if (thumb) thumb.style.left = `${fraction * 100}%`;
      if (time) time.textContent = formatDuration(current);
      if (miniFill) miniFill.style.width = `${fraction * 100}%`;
    });

    // ---------- Загрузка данных ----------

    const CATALOG_PAGE_SIZE = 100;

    async function boot() {
      if (OUTSIDE_TELEGRAM) return;
      mutate({ bootStatus: "loading", bootError: "" });
      try {
        // Язык — до первого рендера, иначе экран загрузки успевает мигнуть русским.
        // Осознанный выбор приедет с сервера ниже и перекроет догадку по профилю.
        const profile = telegramUser();
        setLanguage(profile && profile.language_code);
        await login();
        // Главная показывается сразу после двух лёгких запросов: ей нужен только
        // статус Premium и счётчик библиотеки (= число id). Тяжёлые списки —
        // каталог и страница библиотеки с подписанными ссылками — догружаются фоном.
        // Без Premium сервер отвечает 402 на всё, кроме входа, оплаты и профиля:
        // библиотека тогда пустая, а вместо главной — пэйвол.
        const [libraryIds, statusAtBoot] = await Promise.all([
          getLibraryIds().catch((error) => (error && error.status === 402 ? [] : Promise.reject(error))),
          getPremiumStatus(),
        ]);
        // Пробный период включается сам при первом открытии (решение владельца 15.09):
        // замер — 0 живых входов и 0 оплат, человек упирался в пэйвол и уходил.
        // Сервер выдаёт его один раз на аккаунт; не вышло — показываем пэйвол как раньше.
        let premium = statusAtBoot;
        let trialStarted = false;
        if (premium && !premium.active && premium.trial_available) {
          try {
            premium = await startPremiumTrial();
            trialStarted = Boolean(premium && premium.active);
          } catch {
            premium = statusAtBoot;
          }
        }
        mutate({
          bootStatus: "ready",
          user: telegramUser(),
          libraryIds: new Set(libraryIds),
          libraryTotal: libraryIds.length,
          premium,
        });
        // Сохранённый выбор языка догоняет фоном: если человек уже выбирал язык в
        // боте, приложение подхватит тот же, а не догадку по профилю Telegram.
        getLanguages()
          .then((data) => {
            if (data && data.current && data.current !== getLanguage()) {
              setLanguage(data.current);
              render();
            }
          })
          .catch(() => {});
        if (trialStarted) {
          // Библиотеку грузили до триала и получили 402 — unlockApp догрузит всё
          unlockApp();
          showToast(`${premium.trial_days || 7} дней Premium бесплатно 🎁`);
        } else if (premium && premium.active) {
          loadHeavyData();
          maybeStartOnboarding();
        } else {
          // Пэйволу нужен только профиль (доступен ли триал). Гейт подписки здесь не
          // проверяем: без Premium он обещал «бесплатно, пока подписаны», а после
          // подписки человек всё равно упирался в пэйвол — две стены и враньё.
          loadProfile();
        }
      } catch (error) {
        mutate({
          bootStatus: "error",
          bootError: error && error.message ? error.message : "Не удалось загрузить данные",
        });
      }
    }

    // Premium появился посреди сессии (триал, оплата) — догружаем то, что пэйвол не грузил
    function unlockApp() {
      getLibraryIds()
        .then((ids) => mutate({ libraryIds: new Set(ids), libraryTotal: ids.length }))
        .catch(() => {});
      loadHeavyData();
      maybeStartOnboarding();
    }

    // Premium истёк посреди сессии: сервер ответил 402 — показываем пэйвол
    window.addEventListener("premium-required", () => {
      const { premium } = getState();
      if (premium && premium.active) mutate({ premium: { ...premium, active: false } });
    });

    // Вернулись из кассы ЮKassa: оплата могла пройти, пока приложение было в фоне
    document.addEventListener("visibilitychange", () => {
      const { premium, bootStatus } = getState();
      if (document.visibilityState !== "visible" || bootStatus !== "ready" || !premium || premium.active) {
        return;
      }
      getPremiumStatus()
        .then((fresh) => {
          if (!fresh.active) return;
          mutate({ premium: fresh });
          unlockApp();
        })
        .catch(() => {});
    });

    // Фоновая догрузка: каталог для миксов, страница библиотеки, популярные запросы
    function loadHeavyData() {
      getTracks("", 1, CATALOG_PAGE_SIZE)
        .then((page) => mutate({ catalog: page.items, catalogTotal: page.total }))
        .catch(() => {});
      getLibrary(1)
        .then((page) => mutate({ libraryPageItems: page.items, libraryTotal: page.total }))
        .catch(() => {});
      getPopularQueries()
        .then((queries) => mutate({ popularQueries: queries }))
        .catch(() => {});
      getGenres()
        .then((genres) => mutate({ genres }))
        .catch(() => {});
      // Конкурсы: баннер на главной показывается, только когда розыгрыш идёт
      getContests()
        .then((contests) => mutate({ contests }))
        .catch(() => mutate({ contests: [] }));
      // Профиль нужен главной: доступность триала и начисленные награды
      loadProfile();
      checkSubscriptionGate();
    }

    function refreshContests() {
      getContests()
        .then((contests) => mutate({ contests }))
        .catch(() => {});
    }

    // Участие: сервер сам проверяет условия и возвращает конкурс с новым состоянием.
    // Отказ приходит текстом («подпишитесь», «пригласите друзей») — показываем как есть.
    function joinContestAction(contestId) {
      if (!contestId) return;
      joinContest(contestId)
        .then((result) => {
          const contests = (getState().contests || []).map((item) =>
            item.id === contestId ? result.contest : item
          );
          mutate({ contests });
          showToast("Вы участвуете в розыгрыше 🍀");
        })
        .catch((error) => {
          showToast(error.message || "Не удалось записать вас в конкурс");
          refreshContests();
        });
    }

    // Гейт обязательной подписки (блок B): если не подписан и нет Premium — показываем
    // поверх всего. Premium/админ/пустой список каналов → required=false, гейта нет.
    function checkSubscriptionGate() {
      getSubscriptionStatus(false)
        .then((status) => {
          if (status.required && !status.subscribed) mutate({ subGate: status });
        })
        .catch(() => {});
    }

    // «Я подписался» — перепроверка минуя кэш. Подписан/купил Premium → гейт снимаем.
    function recheckSubscription() {
      getSubscriptionStatus(true)
        .then((status) => {
          if (!status.required || status.subscribed) {
            mutate({ subGate: null });
            showToast("Доступ открыт 🎧");
          } else {
            mutate({ subGate: status });
            showToast("Подписка не найдена — проверьте все каналы");
          }
        })
        .catch(() => showToast("Не удалось проверить подписку"));
    }

    // Онбординг только для новых и ровно один раз. Флаг ставится СРАЗУ при показе
    // (закрыл на середине — больше не мучаем), дублируется в Telegram CloudStorage:
    // localStorage в вебвью Telegram не везде переживает перезапуск, из-за чего
    // онбординг показывался бесконечно.
    async function maybeStartOnboarding() {
      if (isOnboarded()) return;
      // У пользователя уже есть библиотека — он не новый, онбординг не нужен
      if (getState().libraryIds.size > 0) {
        setOnboarded();
        return;
      }
      if (await isOnboardedCloud()) {
        setOnboarded(); // мигрируем облачный флаг в localStorage
        return;
      }
      setOnboarded();
      mutate({ onbActive: true, onbStep: 0 });
      getArtists(24)
        .then((artists) => mutate({ onbArtists: artists.slice(0, 24) }))
        .catch(() => {});
    }

    function advanceOnboarding() {
      const next = getState().onbStep + 1;
      if (next >= 3) {
        finishOnboarding();
        return;
      }
      mutate({ onbStep: next });
    }

    function finishOnboarding() {
      setOnboarded();
      mutate({ onbActive: false });
    }

    let libraryPagesLoaded = 1;
    let libraryPageLoading = null;

    // Двойной тап «Ещё» раньше грузил одну и ту же страницу дважды — в списке
    // появлялись дубли. Пока запрос в пути, повторный вызов ждёт его же.
    function loadMoreLibrary() {
      if (libraryPageLoading) return libraryPageLoading;
      libraryPageLoading = (async () => {
        const next = libraryPagesLoaded + 1;
        const page = await getLibrary(next);
        libraryPagesLoaded = next;
        const state = getState();
        const known = new Set(state.libraryPageItems.map((t) => t.id));
        mutate({
          libraryPageItems: [...state.libraryPageItems, ...page.items.filter((t) => !known.has(t.id))],
          libraryTotal: page.total,
        });
        return page;
      })().finally(() => {
        libraryPageLoading = null;
      });
      return libraryPageLoading;
    }

    async function loadProfile() {
      if (getState().profileStatus === "loading") return;
      mutate({ profileStatus: "loading" });
      try {
        const profile = await getProfile();
        mutate({ profile, profileStatus: "ready" });
        // Сервер начисляет дни Premium за новые достижения — говорим об этом сразу
        if (profile.rewarded_days > 0) {
          showToast(`Достижение выполнено: +${profile.rewarded_days} дн. Premium 🎉`);
          getPremiumStatus()
            .then((premium) => mutate({ premium }))
            .catch(() => {});
        }
      } catch {
        mutate({ profileStatus: "error" });
      }
    }

    async function loadProfileTop() {
      try {
        mutate({ profileTop: await getProfileTop() });
      } catch {
        // блоки топа необязательны
      }
    }

    async function loadReferralTop() {
      try {
        mutate({ referralTop: await getReferralTop() });
      } catch {
        // лидерборд необязателен — молча
      }
    }

    async function loadLyrics(track) {
      try {
        const data = await getLyrics(track.id);
        if (getState().lyricsTrack !== track) return;
        mutate({ lyrics: data, lyricsStatus: "ready", lyricsEditing: false });
      } catch {
        if (getState().lyricsTrack !== track) return;
        mutate({ lyrics: { found: false, text: null }, lyricsStatus: "ready", lyricsEditing: false });
      }
    }

    function saveLyrics() {
      const input = root.querySelector('[data-role="lyrics-input"]');
      const text = input ? input.value.trim() : "";
      if (!text) {
        showToast("Введите текст");
        return;
      }
      const track = getState().lyricsTrack;
      submitLyrics(track.id, text)
        .then((data) => {
          mutate({ lyrics: data, lyricsEditing: false });
          showToast("Текст сохранён");
        })
        .catch(() => showToast("Не удалось сохранить"));
    }

    async function loadPlaylists() {
      navigateTo("playlists", { playlistsStatus: "loading", playlistCreating: false });
      try {
        mutate({ playlists: await getPlaylists(), playlistsStatus: "ready" });
      } catch {
        mutate({ playlistsStatus: "error" });
      }
    }

    async function loadAlbums() {
      navigateTo("albums", { albumsStatus: "loading" });
      try {
        mutate({ albums: await getAlbums(), albumsStatus: "ready" });
      } catch {
        mutate({ albumsStatus: "error" });
      }
    }

    async function loadArtistCard(name) {
      navigateTo("artist", { artistCard: null, artistCardStatus: "loading" });
      try {
        mutate({ artistCard: await getArtistCard(name), artistCardStatus: "ready" });
      } catch {
        mutate({ artistCardStatus: "error" });
      }
    }

    async function loadMyArtists() {
      navigateTo("myartists", { myArtistsStatus: "loading" });
      try {
        mutate({ myArtists: await getMyArtists(), myArtistsStatus: "ready" });
      } catch {
        mutate({ myArtists: [], myArtistsStatus: "ready" });
      }
    }

    // Подписка на артиста из карточки: оптимистично меняем флаг, шлём запрос
    async function toggleFollowArtist(artistId) {
      const card = getState().artistCard;
      if (!card) return;
      const next = !card.following;
      mutate({ artistCard: { ...card, following: next } });
      try {
        await (next ? followArtist(artistId) : unfollowArtist(artistId));
        showToast(next ? "Вы подписались на артиста" : "Вы отписались");
      } catch {
        mutate({ artistCard: { ...getState().artistCard, following: !next } });
        showToast("Не удалось изменить подписку");
      }
    }

    async function unfollowArtistAction(artistId) {
      try {
        await unfollowArtist(artistId);
        mutate({ myArtists: getState().myArtists.filter((a) => a.id !== artistId) });
      } catch {
        showToast("Не удалось отписаться");
      }
    }

    async function loadArtists() {
      navigateTo("artists", { artistsStatus: "loading" });
      try {
        mutate({ artists: await getArtists(), artistsStatus: "ready" });
      } catch {
        mutate({ artists: [], artistsStatus: "ready" });
      }
    }

    async function openCollection(title, type, fetcher) {
      navigateTo("collection", {
        collectionTitle: title,
        collectionType: type,
        collectionTracks: [],
        collectionLive: [],
        collectionAlbumId: null,
        collectionCover: null,
        collectionStatus: "loading",
      });
      try {
        mutate({ collectionTracks: await fetcher(), collectionStatus: "ready" });
      } catch {
        mutate({ collectionTracks: [], collectionStatus: "ready" });
      }
    }

    let searchTimer = null;
    let searchSeq = 0;

    // Открытие приложения — начало сессии для отчёта аналитики (длительность считает
    // сервер по промежуткам между событиями). Уйдёт первой пачкой, когда будет токен.
    trackClient("app_open");

    // Запрос логируется с числом результатов, а оно известно только после ответа.
    // Enter нажали, пока поиск шёл, — запоминаем и логируем по приходу выдачи.
    let pendingSearchLog = null;

    function commitSearchLog(value) {
      const state = getState();
      if (state.searchStatus === "done" && (state.searchQuery || "").trim() === value) {
        logSearchQuery(value, state.searchTotal || 0);
      } else {
        pendingSearchLog = value;
      }
    }

    function settleSearchLog(query, results) {
      if (pendingSearchLog === null || pendingSearchLog !== query.trim()) return;
      pendingSearchLog = null;
      logSearchQuery(query.trim(), results);
    }

    function scheduleSearch(query) {
      const state = getState();
      state.searchQuery = query;
      clearTimeout(searchTimer);
      const seq = ++searchSeq;
      if (!query.trim()) {
        mutateSearch({ searchResults: [], liveResults: [], searchTotal: 0, searchStatus: "idle" });
        return;
      }
      mutateSearch({ searchStatus: "loading" });
      searchTimer = setTimeout(async () => {
        try {
          // Треки — секционная выдача (Артисты/Альбомы/Плейлисты/Треки), минусы — плоский список
          if (getState().searchMode === "instrumentals") {
            const page = await getInstrumentals(query.trim(), 1, 50);
            if (seq !== searchSeq) return;
            mutateSearch({
              searchResults: page.items, searchTotal: page.total,
              searchSections: null, searchStatus: "done",
            });
            settleSearchLog(query, page.total || 0);
            return;
          }
          // Треки берём живьём из источников, артистов/альбомы/плейлисты — из базы.
          // Оба запроса параллельно: живой поиск не должен ждать локальные секции.
          const [sections, live, albums] = await Promise.all([
            searchAll(query.trim()).catch(() => null),
            liveSearch(query.trim()).catch(() => ({ items: [] })),
            // Альбомы — третьим параллельным запросом: выдача треков их не ждёт дольше
            searchLiveAlbums(query.trim()).catch(() => []),
          ]);
          if (seq !== searchSeq) return; // пришёл более свежий запрос
          mutateSearch({
            searchSections: sections,
            liveAlbums: albums || [],
            liveResults: live.items,
            searchResults: live.items,
            searchTotal: live.items.length,
            searchStatus: "done",
          });
          settleSearchLog(query, live.items.length);
        } catch {
          if (seq !== searchSeq) return;
          mutateSearch({
            searchResults: [], liveResults: [], searchSections: null,
            searchTotal: 0, searchStatus: "done",
          });
          settleSearchLog(query, null); // поиск упал — «пусто» здесь не ответ источника
        }
      }, 300);
    }

    // Кандидат живого поиска в вид, понятный плееру. Уже залитый трек играем по его
    // id обычной подписанной ссылкой; новый — потоком, а в фон ставим закачку, чтобы
    // Альбом из живого поиска (16.09): экран подборки, треки играют потоком по номеру.
    // Отдельно от openCollection: у живых треков id вида «live:…», и обычные строки
    // подборки, которые ищут трек по числовому id, их бы не проиграли.
    async function openLiveAlbum(album) {
      navigateTo("collection", {
        collectionTitle: `${album.artist} — ${album.title}`,
        collectionType: "album",
        collectionTracks: [],
        collectionLive: [],
        collectionAlbumId: album.id,
        collectionCover: album.cover_url || null,
        collectionStatus: "loading",
      });
      try {
        const { items } = await getLiveAlbumTracks(album.id);
        mutate({ collectionLive: items, collectionTracks: items.map(liveTrack), collectionStatus: "ready" });
      } catch {
        mutate({ collectionLive: [], collectionTracks: [], collectionStatus: "ready" });
        showToast("Не удалось открыть альбом — попробуйте позже");
      }
    }

    let albumAddRunning = false;

    async function addWholeAlbum() {
      const { collectionAlbumId, collectionLive } = getState();
      if (!collectionAlbumId || albumAddRunning) return;
      albumAddRunning = true;
      try {
        const result = await addLiveAlbumToLibrary(collectionAlbumId);
        showToast(`Добавляю альбом в библиотеку: ${result.count} тр., около ${result.minutes} мин`);
      } catch (error) {
        showToast(error && error.status === 409 ? "Альбом уже добавляется — дождитесь окончания" : "Не удалось добавить альбом");
      } finally {
        albumAddRunning = false;
      }
      return collectionLive;
    }

    // со следующего раза он играл мгновенно у всех и лежал в библиотеке.
    function liveTrack(item) {
      if (item.track_id) {
        return {
          id: item.track_id,
          title: item.title,
          artist: item.artist,
          duration: item.duration,
          cover_url: item.cover_url,
          live_ref: item.ref,
        };
      }
      return {
        id: `live:${item.ref}`,
        title: item.title,
        artist: item.artist,
        duration: item.duration,
        cover_url: item.cover_url,
        audio_url: liveStreamUrl(item.ref),
        live_ref: item.ref,
      };
    }

    // Поиск обновляет только контейнер результатов — без полного рендера.
    function mutateSearch(patch) {
      Object.assign(getState(), patch);
      const container = document.getElementById("search-results");
      if (container) container.innerHTML = renderSearchResults(getState());
    }

    // Запуск поиска по чипу: подставляем в инпут, сохраняем в недавние + лог на сервер.
    function runSearch(query) {
      const value = (query || "").trim();
      if (!value) return;
      const input = root.querySelector('[data-role="search-input"]');
      if (input) input.value = value;
      pushRecentSearch(value);
      pendingSearchLog = value; // лог уйдёт с числом результатов, когда поиск ответит
      scheduleSearch(value);
    }

    // «Мои треки»: ввод в поиске перерисовывает только тело списка (фокус живёт)
    function refreshMyTracksBody() {
      const container = document.getElementById("mytracks-body");
      if (container) container.innerHTML = renderMyTracksBody(getState());
    }

    // «Скачать всё» (шит Моих треков, скрин VK): офлайн-кэш всей библиотеки — Premium.
    let downloadAllRunning = false;

    async function downloadAllTracks() {
      mutate({ myTracksMenuOpen: false });
      if (downloadAllRunning) {
        showToast("Скачивание уже идёт");
        return;
      }
      downloadAllRunning = true;
      try {
        await downloadAllTracksNow();
      } finally {
        downloadAllRunning = false;
      }
    }

    async function downloadAllTracksNow() {
      const state = getState();
      if (!state.premium || !state.premium.active) {
        showToast("Скачивание треков — с Premium");
        navigateTo("premium");
        return;
      }
      if (!offlineSupported()) {
        showToast("Офлайн-кэш недоступен на этом устройстве");
        return;
      }
      // «Скачать всё» раньше брало только загруженную страницу библиотеки (первые
      // 100): у кого треков больше, остальные молча не скачивались. Догружаем все.
      try {
        while (getState().libraryPageItems.length < getState().libraryTotal) {
          const page = await loadMoreLibrary();
          if (!page || !page.items.length) break;
        }
      } catch {
        showToast("Не удалось получить весь список — скачаю то, что загружено");
      }
      const list = myTracksList(getState()).filter((t) => t.id > 0 && !isOffline(t.id));
      if (!list.length) {
        showToast("Всё уже скачано");
        return;
      }
      showToast(`Скачиваю ${list.length} треков…`);
      let done = 0;
      let failed = 0;
      for (const track of list) {
        try {
          if (!track.audio_url) {
            const fresh = await getTrackById(track.id);
            track.audio_url = fresh.audio_url;
          }
          await saveOffline(track, resolveAudioUrl(track));
          done += 1;
          if (done % 10 === 0) showToast(`Скачано ${done} из ${list.length}…`);
        } catch {
          failed += 1;
        }
      }
      showToast(failed ? `Скачано ${done}, не удалось ${failed}` : `Скачано ${done} треков`);
      mutate({});
    }

    async function activateTrial() {
      try {
        const premium = await startPremiumTrial();
        mutate({ premium });
        loadProfile(); // trial_available и достижения пересчитываются на сервере
        // Без числа дней в коде: срок задаёт сервер (TRIAL_DAYS, приходит в trial_days)
        showToast("Пробный Premium активирован 🎁");
      } catch (error) {
        showToast((error && error.message) || "Не удалось активировать пробный период");
      }
    }

    async function startPlaylistTransfer() {
      const input = root.querySelector('[data-role="transfer-input"]');
      const source = input ? input.value.trim() : "";
      if (!source) {
        showToast("Вставьте ссылку или список треков");
        return;
      }
      mutate({ transferSource: source, transferStatus: "loading", transferResult: "" });
      try {
        const result = await startTransfer(source);
        // ⚠️ preview — названия треков из ЧУЖОГО плейлиста Spotify/Яндекса. Без
        // экранирования трек с названием «<img onerror=…>» исполнял код в Mini App
        // того, кто переносит, — вплоть до кражи initData и входа в его аккаунт.
        const skipped = result.skipped
          ? `<br>Лимит одного переноса — ${result.queued}, ещё ${result.skipped} не вошли.`
          : "";
        mutate({
          transferStatus: "idle",
          transferResult:
            `Принято треков: ${result.queued}. Переношу — отчёт придёт в чат бота.${skipped}` +
            (result.preview.length ? `<br><br>${result.preview.map(escapeHtml).join("<br>")}` : ""),
        });
        showToast(`Переношу ${result.queued} треков`);
      } catch (error) {
        mutate({
          transferStatus: "idle",
          transferResult: escapeHtml(
            (error && error.message) ||
              "Не удалось прочитать список. Проверьте ссылку или пришлите треки текстом."
          ),
        });
      }
    }

    async function clearAllOffline() {
      const tracks = offlineTracks();
      mutate({ myTracksMenuOpen: false });
      if (!tracks.length) {
        showToast("Скачанных треков нет");
        return;
      }
      for (const track of tracks) {
        await removeOffline(track.id);
      }
      showToast("Скачанные треки удалены");
      mutate({});
    }

    function contextTracks(context) {
      const state = getState();
      if (context === "search") return state.searchResults;
      if (context === "library") return state.libraryPageItems;
      if (context === "mytracks") return myTracksList(state);
      if (context === "recent") return getRecentTracks();
      if (context === "offline") return offlineTracks();
      if (context === "collection") return state.collectionTracks;
      if (context === "profile-top") return (state.profileTop && state.profileTop.tracks) || [];
      return state.catalog;
    }

    // Точечное обновление кнопок «в библиотеке» — без полного рендера (ТЗ §10: без мерцания)
    function refreshLibraryButtons(trackId, inLibrary) {
      root.querySelectorAll(`[data-action="toggle-library"][data-id="${trackId}"]`).forEach((btn) => {
        btn.classList.toggle("is-added", inLibrary);
        btn.classList.toggle("is-active", inLibrary);
        btn.innerHTML = icon(inLibrary ? "check" : "plus");
      });
    }

    // Треки, по которым запрос библиотеки ещё в пути. Двойной тап раньше слал POST и
    // DELETE одновременно: сервер мог применить их в обратном порядке, и интерфейс
    // показывал «не в библиотеке» при треке в библиотеке.
    const libraryInFlight = new Set();

    async function handleToggleLibrary(trackId, fromSheet) {
      if (fromSheet) closeSheet();
      if (!trackId || trackId < 0) return; // минусы в библиотеку не добавляются
      if (libraryInFlight.has(trackId)) return;
      libraryInFlight.add(trackId);
      try {
        await toggleLibraryNow(trackId, fromSheet);
      } finally {
        libraryInFlight.delete(trackId);
      }
    }

    async function toggleLibraryNow(trackId, fromSheet) {
      const state = getState();
      const prevIds = state.libraryIds;
      const inLibrary = prevIds.has(trackId);
      // Оптимистично: интерфейс мгновенный, при ошибке откатываем
      const nextIds = new Set(prevIds);
      if (inLibrary) nextIds.delete(trackId);
      else nextIds.add(trackId);
      state.libraryIds = nextIds;
      if (fromSheet) {
        // шит закрылся — нужен полный рендер, иначе кнопки под ним не обновятся
        mutate({});
      } else {
        refreshLibraryButtons(trackId, !inLibrary);
      }
      try {
        if (inLibrary) {
          await removeFromLibrary(trackId);
          const current = getState();
          current.libraryPageItems = current.libraryPageItems.filter((t) => t.id !== trackId);
          current.libraryTotal = Math.max(0, current.libraryTotal - 1);
          if (current.screen === "mytracks") refreshMyTracksBody();
        } else {
          await addToLibrary(trackId);
          const track = findTrack(trackId);
          const current = getState();
          if (track && !current.libraryPageItems.some((t) => t.id === trackId)) {
            current.libraryPageItems = [track, ...current.libraryPageItems];
            current.libraryTotal += 1;
          }
          showToast("Добавлено в библиотеку");
        }
      } catch {
        getState().libraryIds = prevIds;
        refreshLibraryButtons(trackId, inLibrary);
        showToast("Не получилось — попробуйте ещё раз");
      }
    }

    // Двойной тап по «Оплатить» создавал два платежа в кассе и открывал две вкладки
    let paymentInFlight = false;

    async function handlePayPremium() {
      if (paymentInFlight) return;
      paymentInFlight = true;
      try {
        const months = getState().premiumMonths || 1;
        const { confirmation_url: url } = await createPaymentLink(months);
        if (tg) tg.openLink(url);
        else window.open(url, "_blank");
      } catch {
        showToast("Оплата временно недоступна");
      } finally {
        paymentInFlight = false;
      }
    }

    // «Скачать» (ТЗ §9): бот присылает аудиофайл в чат — без браузера и Google
    async function handleDownload(trackId) {
      closeSheet();
      if (!trackId || trackId < 0) {
        showToast("Минусы скачиваются в поиске бота");
        return;
      }
      showToast("Отправляю файл в чат…");
      try {
        await sendTrackToChat(trackId);
        showToast("Готово! Файл у вас в чате с ботом");
      } catch (error) {
        showToast(
          error && error.status === 409
            ? "Файл ещё обрабатывается — попробуйте позже"
            : "Не удалось отправить — попробуйте позже"
        );
      }
    }

    function findTrack(trackId) {
      const state = getState();
      return (
        state.catalog.find((t) => t.id === trackId) ||
        state.searchResults.find((t) => t.id === trackId) ||
        state.libraryPageItems.find((t) => t.id === trackId) ||
        getRecentTracks().find((t) => t.id === trackId) ||
        offlineTracks().find((t) => t.id === trackId) ||
        (state.collectionTracks || []).find((t) => t.id === trackId) ||
        ((state.profileTop && state.profileTop.tracks) || []).find((t) => t.id === trackId) ||
        (state.artistCard ? artistCardTracks(state.artistCard).find((t) => t.id === trackId) : null) ||
        (state.currentTrack && state.currentTrack.id === trackId ? state.currentTrack : null)
      );
    }

    // Все треки, отрисованные на карточке артиста (топ + синглы + последний релиз)
    function artistCardTracks(card) {
      return [
        ...(card.top_tracks || []),
        ...(card.singles || []),
        ...(card.latest_release ? [card.latest_release] : []),
      ];
    }

    function toggleOffline(trackId) {
      const track = findTrack(trackId);
      if (!track) return;
      closeSheet();
      if (isOffline(trackId)) {
        removeOffline(trackId).then(() => showToast("Удалено из офлайна"));
        return;
      }
      const url = resolveAudioUrl(track);
      const absolute = url && url.startsWith("http") ? url : location.origin + url;
      showToast("Сохраняю офлайн…");
      saveOffline(track, absolute)
        .then(() => showToast("Сохранено офлайн"))
        .catch(() => showToast("Не удалось сохранить офлайн"));
    }

    function openLyrics(trackId) {
      const track = findTrack(trackId);
      if (!track || track.id < 0) return;
      closeSheet();
      closePlayer(); // иначе оверлей плеера закрывает экран текста (ТЗ §8)
      navigateTo("lyrics", {
        lyricsTrack: track,
        lyrics: null,
        lyricsStatus: "loading",
        lyricsEditing: false,
      });
      loadLyrics(track);
    }

    // «Создать новый плейлист» прямо из шита выбора: создаём и сразу кладём трек
    function openCreatePlaylistForPicker() {
      const trackId = getState().playlistPickerTrack;
      const title = (window.prompt("Название плейлиста") || "").trim();
      if (!title) return;
      createPlaylist(title)
        .then(async (playlist) => {
          await addTrackToPlaylist(playlist.id, trackId);
          mutate({ playlistPickerTrack: null, playlists: await getPlaylists() });
          showToast("Плейлист создан, трек добавлен");
        })
        .catch(() => showToast("Не удалось создать плейлист"));
    }

    function submitCreatePlaylist() {
      const input = root.querySelector('[data-role="playlist-title"]');
      const title = input ? input.value.trim() : "";
      if (!title) {
        showToast("Введите название");
        return;
      }
      createPlaylist(title)
        .then(async () => {
          mutate({ playlistCreating: false });
          showToast("Плейлист создан");
          try {
            mutate({ playlists: await getPlaylists() });
          } catch {
            // список обновится при следующем открытии
          }
        })
        .catch((error) =>
          showToast(error && error.status === 403 ? "Лимит плейлистов — нужен Premium" : "Не удалось создать")
        );
    }

    function copyText(text) {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(
          () => showToast("Ссылка скопирована"),
          () => showToast("Не удалось скопировать")
        );
        return;
      }
      showToast("Не удалось скопировать");
    }

    function mixTracks(mix) {
      const state = getState();
      if (mix === "library" || mix === "library-shuffle") return state.libraryPageItems;
      return state.catalog; // catalog | discover
    }

    // ---------- События ----------

    root.addEventListener("click", (event) => {
      const el = event.target.closest("[data-action]");
      if (!el) return;
      const action = el.dataset.action;
      if (action === "noop") {
        event.stopPropagation();
        return;
      }
      const id = el.dataset.id ? Number(el.dataset.id) : null;
      hapticTap();

      switch (action) {
        case "retry-boot":
          boot();
          break;
        case "sub-recheck":
          recheckSubscription();
          break;
        case "sub-click":
          // не preventDefault — ссылка канала откроется браузером, клик логируем в фоне
          if (el.dataset.cid) logChannelClick(Number(el.dataset.cid)).catch(() => {});
          break;
        case "sub-premium":
          mutate({ subGate: null });
          navigateTo("premium");
          break;
        case "search-web": {
          const q = getState().searchQuery.trim();
          if (!q) break;
          fetchFromWeb(q)
            .then(() => showToast("Ищем — трек придёт в бота и в вашу библиотеку 🎧"))
            .catch(() => showToast("Поиск временно недоступен"));
          break;
        }
        case "nav":
          resetToTab(el.dataset.screen);
          break;
        case "back":
          goBack();
          break;
        case "open-settings":
          navigateTo("settings");
          break;
        case "open-profile":
          navigateTo("profile");
          loadProfile();
          loadProfileTop();
          break;
        case "open-achievements":
          navigateTo("achievements");
          if (!getState().profile) loadProfile();
          break;
        case "open-referral":
          navigateTo("referral");
          if (!getState().profile) loadProfile();
          loadReferralTop();
          break;
        case "open-premium":
          navigateTo("premium");
          break;
        case "paywall-trial":
          // Пробный период — после активации приложение открывается сразу
          startPremiumTrial()
            .then((premium) => {
              mutate({ premium });
              showToast(`Доступ открыт на ${premium.trial_days || 7} дней`);
              unlockApp();
            })
            .catch(() => showToast("Не удалось активировать — попробуйте позже"));
          break;
        case "paywall-buy":
          mutate({ premiumMonths: 1 });
          handlePayPremium();
          break;
        case "open-contests":
          navigateTo("contests");
          refreshContests();
          break;
        case "contest-join":
          joinContestAction(Number(el.dataset.id));
          break;
        case "premium-plan":
          mutate({ premiumMonths: Number(el.dataset.months) || 1 });
          break;
        case "open-mytracks":
          navigateTo("mytracks", { myTracksQuery: "", myTracksEdit: false, sortSheetOpen: false });
          break;
        case "mytracks-tab":
          mutate({ myTracksTab: el.dataset.tab });
          break;
        case "mytracks-edit":
          mutate({ myTracksEdit: !getState().myTracksEdit });
          break;
        case "mytracks-remove":
          event.stopPropagation();
          handleToggleLibrary(id, false);
          break;
        case "mytracks-shuffle":
          playMix(myTracksList(getState()), "Здесь пока нет треков");
          break;
        case "open-sort-sheet":
          mutate({ sortSheetOpen: true });
          break;
        case "close-sort-sheet":
          mutate({ sortSheetOpen: false });
          break;
        case "mytracks-sort":
          event.stopPropagation();
          mutate({ myTracksSort: el.dataset.value, sortSheetOpen: false });
          break;
        case "invite-friend": {
          const profile = getState().profile;
          if (!profile) break;
          trackClient("share_click", { props: { kind: "referral" } });
          const shareUrl = `https://t.me/share/url?url=${encodeURIComponent(profile.referral.link)}&text=${encodeURIComponent("Слушай музыку в Infinity Music 🎧")}`;
          if (tg) tg.openTelegramLink(shareUrl);
          else window.open(shareUrl, "_blank");
          break;
        }
        case "copy-referral":
          copyText(el.dataset.link);
          break;
        case "play-mix": {
          const mix = el.dataset.mix;
          const msg = mix.startsWith("library") ? "Добавьте треки в библиотеку" : "В базе пока нет треков";
          playMix(mixTracks(mix), msg);
          break;
        }
        case "open-artists":
          loadArtists();
          break;
        case "open-artist":
          loadArtistCard(el.dataset.artist);
          break;
        case "open-artist-tracks": {
          const name = el.dataset.artist;
          openCollection(name, "artist", () => getArtistTracks(name));
          break;
        }
        case "artist-play-all": {
          const name = el.dataset.artist;
          getArtistTracks(name)
            .then((tracks) => playMix(tracks, "У артиста пока нет треков"))
            .catch(() => showToast("Не удалось загрузить треки"));
          break;
        }
        case "artist-play-similar": {
          // «Слушать похожее»: очередь = свои треки артиста + общий микс (микс по артисту)
          const name = el.dataset.artist;
          Promise.all([getArtistTracks(name), getMix({})])
            .then(([own, mix]) => {
              const seen = new Set();
              const pool = [...own, ...mix].filter((t) => !seen.has(t.id) && seen.add(t.id));
              playMix(pool, "Пока нечего рекомендовать");
            })
            .catch(() => showToast("Не удалось собрать микс"));
          break;
        }
        case "toggle-follow":
          toggleFollowArtist(id);
          break;
        case "open-my-artists":
          loadMyArtists();
          break;
        case "unfollow-artist":
          event.stopPropagation();
          unfollowArtistAction(id);
          break;
        case "open-genre":
          openCollection(el.dataset.name, "genre", () =>
            getGenreTracks(el.dataset.slug).then((page) => page.items)
          );
          break;
        case "open-doc":
          navigateTo("docs", { docKey: el.dataset.doc });
          break;
        case "toggle-artist":
          event.stopPropagation();
          toggleFavoriteArtist(el.dataset.artist);
          mutate({});
          break;
        case "open-lyrics":
          event.stopPropagation();
          openLyrics(id);
          break;
        case "lyrics-edit":
          mutate({ lyricsEditing: true });
          break;
        case "lyrics-cancel":
          mutate({ lyricsEditing: false });
          break;
        case "lyrics-save":
          saveLyrics();
          break;
        case "toggle-offline":
          event.stopPropagation();
          toggleOffline(id);
          break;
        case "open-downloads":
          navigateTo("mytracks", { myTracksTab: "downloaded", myTracksQuery: "", myTracksEdit: false });
          break;
        case "play-recommended":
          playRecommended();
          break;
        case "play-vibe":
          // mood-микс с карточки «Какой сейчас вайб?» — тот же движок, что «Настроить»
          playVibe(el.dataset.mood);
          break;
        case "open-equalizer":
          navigateTo("equalizer");
          break;
        case "open-queue":
          mutate({ queueOpen: true });
          break;
        case "close-queue":
          mutate({ queueOpen: false });
          break;
        case "queue-jump":
          playQueueIndex(Number(el.dataset.index));
          mutate({ queueOpen: false });
          break;
        case "toggle-repeat":
          toggleRepeat();
          break;
        case "open-player-settings":
          mutate({ playerSettingsOpen: true });
          break;
        case "close-player-settings":
          mutate({ playerSettingsOpen: false });
          break;
        case "sleep-set":
          setSleepTimer(Number(el.dataset.min));
          mutate({ playerSettingsOpen: false });
          break;
        case "open-equalizer-from-player":
          closePlayer();
          navigateTo("equalizer");
          break;
        case "play-track-mix": {
          const track = findTrack(id);
          if (track) playTrackMix(track);
          break;
        }
        case "queue-add": {
          const track = findTrack(id);
          if (track) addToQueue(track);
          closeSheet();
          break;
        }
        case "queue-next": {
          const track = findTrack(id);
          if (track) playNextInQueue(track);
          closeSheet();
          break;
        }
        case "sheet-open-artist": {
          const artist = el.dataset.artist;
          closeSheet();
          if (artist) loadArtistCard(artist);
          break;
        }
        case "add-to-playlist":
          // шит выбора плейлиста (плейлисты грузим, если ещё не загружены)
          mutate({ playlistPickerTrack: id, sheetTrack: null });
          if (!getState().playlists.length) {
            getPlaylists().then((pl) => mutate({ playlists: pl })).catch(() => {});
          }
          break;
        case "close-playlist-picker":
          mutate({ playlistPickerTrack: null });
          break;
        case "picker-add": {
          const trackId = getState().playlistPickerTrack;
          addTrackToPlaylist(Number(el.dataset.playlist), trackId)
            .then(() => showToast("Добавлено в плейлист"))
            .catch(() => showToast("Не удалось добавить"));
          mutate({ playlistPickerTrack: null });
          break;
        }
        case "picker-create":
          openCreatePlaylistForPicker();
          break;
        case "open-interface":
          navigateTo("interface");
          break;
        case "open-language":
          navigateTo("language");
          break;
        case "set-language": {
          const code = el.dataset.code;
          if (code) {
            setLanguage(code);
            saveLanguage(code).catch(() => {});
            render();
          }
          break;
        }
        case "open-storage":
          navigateTo("storage");
          break;
        case "open-transfer":
          navigateTo("transfer", { transferResult: "", transferStatus: "idle" });
          break;
        case "onb-next":
          advanceOnboarding();
          break;
        case "onb-artist":
          toggleFavoriteArtist(el.dataset.name);
          mutate({});
          break;
        case "onb-import":
          finishOnboarding();
          navigateTo("transfer", { transferResult: "", transferStatus: "idle" });
          break;
        case "onb-finish":
          finishOnboarding();
          break;
        case "open-upload":
          navigateTo("upload", {
            upload: { file: null, fileName: "", title: "", artist: "", status: "idle", result: "" },
          });
          break;
        case "upload-submit":
          submitUpload();
          break;
        case "start-trial":
          event.stopPropagation();
          activateTrial();
          break;
        case "transfer-service":
          mutate({ transferService: el.dataset.value });
          break;
        case "transfer-start":
          startPlaylistTransfer();
          break;
        case "eq-toggle": {
          const eq = getEqSettings();
          saveEqSettings({ ...eq, enabled: !eq.enabled });
          applyEqualizer();
          mutate({});
          break;
        }
        case "eq-preset": {
          saveEqSettings({ ...getEqSettings(), preset: el.dataset.value });
          applyEqualizer();
          mutate({});
          break;
        }
        case "set-accent": {
          saveUiSettings({ ...getUiSettings(), accent: el.dataset.value });
          applyAccent(el.dataset.value);
          mutate({});
          break;
        }
        case "toggle-haptic": {
          const ui = getUiSettings();
          saveUiSettings({ ...ui, haptic: !ui.haptic });
          mutate({});
          break;
        }
        case "open-mytracks-menu":
          mutate({ myTracksMenuOpen: true });
          break;
        case "close-mytracks-menu":
          mutate({ myTracksMenuOpen: false });
          break;
        case "mytracks-edit-from-menu":
          mutate({ myTracksMenuOpen: false, myTracksEdit: true });
          break;
        case "mytracks-download-all":
          downloadAllTracks();
          break;
        case "clear-offline":
          clearAllOffline();
          break;
        case "hero-prev":
        case "hero-next": {
          // стрелки в подсказке: на ПК свайпа нет, листаем миксы кликом
          event.stopPropagation();
          const heroTrack = document.querySelector('[data-role="hero-scroll"]');
          if (heroTrack) {
            // без behavior:smooth — в части встроенных браузеров он no-op на snap-лентах
            const delta = action === "hero-next" ? heroTrack.clientWidth : -heroTrack.clientWidth;
            heroTrack.scrollBy({ left: delta });
          }
          break;
        }
        case "open-recommendations":
          event.stopPropagation();
          navigateTo("recommendations");
          break;
        case "open-playlists":
          loadPlaylists();
          break;
        case "playlist-create":
          mutate({ playlistCreating: true });
          break;
        case "playlist-create-cancel":
          mutate({ playlistCreating: false });
          break;
        case "playlist-create-submit":
          submitCreatePlaylist();
          break;
        case "open-albums":
          loadAlbums();
          break;
        case "open-playlist":
          openCollection(el.dataset.title || "Плейлист", "playlist", () => getPlaylistTracks(id));
          break;
        case "open-album":
          openCollection(el.dataset.name, "album", () => getAlbumTracks(el.dataset.name));
          break;
        case "collection-play": {
          const tracks = getState().collectionTracks;
          if (!tracks.length) break;
          playTrack(tracks[0], tracks);
          openPlayer();
          break;
        }
        case "collection-shuffle":
          playMix(getState().collectionTracks, "Здесь пока пусто");
          break;
        case "open-recent":
          navigateTo("recent");
          break;
        case "set-mood":
        case "set-recog":
        case "set-lang": {
          const key = action === "set-mood" ? "mood" : action === "set-recog" ? "recognizability" : "language";
          const value = el.dataset.value;
          const draft = getState().recDraft;
          mutate({ recDraft: { ...draft, [key]: draft[key] === value ? "" : value } });
          break;
        }
        case "apply-rec":
          saveRecSettings(getState().recDraft);
          goBack();
          playRecommended();
          break;
        case "clear-rec":
          clearRecSettings();
          mutate({ recDraft: { mood: "", recognizability: "", language: "" } });
          showToast("Настройки сброшены");
          break;
        case "dismiss-sub":
          event.stopPropagation();
          mutate({ subDismissed: true });
          break;
        case "search-chip":
          runSearch(el.dataset.q);
          break;
        case "search-mode": {
          const mode = el.dataset.mode;
          if (getState().searchMode === mode) break;
          mutate({ searchMode: mode, searchResults: [], searchTotal: 0, searchStatus: "idle" });
          const currentQuery = getState().searchQuery;
          if (currentQuery.trim()) scheduleSearch(currentQuery); // перезапустить в новом режиме
          break;
        }
        case "clear-recent-searches":
          clearRecentSearches();
          mutateSearch({});
          break;
        case "play-track": {
          if (getState().myTracksEdit && el.dataset.context === "mytracks") break;
          const track = findTrack(id);
          if (!track) return;
          playTrack(track, contextTracks(el.dataset.context));
          openPlayer();
          break;
        }
        case "open-live-album": {
          const album = (getState().liveAlbums || [])[Number(el.dataset.index)];
          if (album) openLiveAlbum(album);
          break;
        }
        case "play-album-live": {
          const items = getState().collectionLive || [];
          const chosen = items[Number(el.dataset.index)];
          if (!chosen) break;
          if (!chosen.track_id) queueLiveFetch(chosen.ref).catch(() => {});
          playTrack(liveTrack(chosen), items.map(liveTrack));
          openPlayer();
          break;
        }
        case "album-add-all":
          addWholeAlbum();
          break;
        case "play-live": {
          const items = getState().liveResults || [];
          const index = Number(el.dataset.index);
          const chosen = items[index];
          if (!chosen) break;
          // Закачку ставим только выбранному: очередь из 30 кандидатов не должна
          // превратиться в 30 фоновых загрузок на боксе 961 МБ
          if (!chosen.track_id) queueLiveFetch(chosen.ref).catch(() => {});
          playTrack(liveTrack(chosen), items.map(liveTrack));
          openPlayer();
          break;
        }
        case "toggle-library":
          event.stopPropagation();
          handleToggleLibrary(id, el.dataset.fromSheet === "1");
          break;
        case "open-sheet": {
          event.stopPropagation();
          const track = findTrack(id);
          if (track) openSheet(track);
          break;
        }
        case "close-sheet":
          closeSheet();
          break;
        case "open-player":
          openPlayer();
          break;
        case "close-player":
          closePlayer();
          break;
        case "toggle-play":
          togglePlay();
          if (el.dataset.stop) event.stopPropagation();
          break;
        case "next":
          playNext();
          break;
        case "prev":
          playPrev();
          break;
        case "toggle-shuffle":
          toggleShuffle();
          break;
        case "seek":
          break; // перемотка — через pointer-drag ниже, не через click
        case "download":
          event.stopPropagation();
          handleDownload(id);
          break;
        case "share": {
          const track = findTrack(id);
          if (track) {
            trackClient("share_click", { trackId: track.id, props: { kind: "track" } });
            const shareUrl = `https://t.me/share/url?url=${encodeURIComponent(`https://t.me/${BOT_USERNAME}?start=track_${track.id}`)}&text=${encodeURIComponent(`${track.artist} — ${track.title}`)}`;
            if (tg) tg.openTelegramLink(shareUrl);
            else window.open(shareUrl, "_blank");
          }
          closeSheet();
          break;
        }
        case "library-more":
          loadMoreLibrary().catch(() => showToast("Не удалось загрузить"));
          break;
        case "pay-premium":
          handlePayPremium();
          break;
        case "open-support":
          // Бот поддержки (блок F): жалобы/отзывы/идеи с медиа
          if (tg) tg.openTelegramLink("https://t.me/suptgmusic_bot");
          else window.open("https://t.me/suptgmusic_bot", "_blank");
          break;
        case "open-bot":
          if (tg) tg.openTelegramLink(`https://t.me/${BOT_USERNAME}`);
          else window.open(`https://t.me/${BOT_USERNAME}`, "_blank");
          break;
        default:
          break;
      }
    });

    root.addEventListener("input", (event) => {
      const role = event.target.dataset ? event.target.dataset.role : null;
      if (role === "search-input") {
        scheduleSearch(event.target.value);
      }
      if (role === "mytracks-search") {
        getState().myTracksQuery = event.target.value;
        refreshMyTracksBody();
      }
      if (role === "eq-band") {
        // Движение ползунка меняет звук сразу, без полного ре-рендера (фокус/драг живут)
        const eq = getEqSettings();
        const gains = [...currentGains(eq)];
        gains[Number(event.target.dataset.band)] = Number(event.target.value);
        saveEqSettings({ ...eq, preset: "custom", custom: gains });
        applyEqualizer();
      }
    });

    // Отпустили ползунок эквалайзера — обновить галочку «Пользовательская» в списке
    root.addEventListener("change", (event) => {
      const role = event.target.dataset ? event.target.dataset.role : null;
      if (role === "eq-band") {
        mutate({});
      }
      if (role === "upload-file") {
        const file = event.target.files && event.target.files[0];
        if (!file) return;
        pendingUploadFile = file;
        // Подставим имя файла в название, если пользователь ещё не ввёл своё
        const title = getState().upload.title || file.name.replace(/\.[^.]+$/, "");
        mutate({ upload: { ...getState().upload, fileName: file.name, title, result: "" } });
      }
    });

    let pendingUploadFile = null;

    async function submitUpload() {
      const titleEl = root.querySelector('[data-role="upload-title"]');
      const artistEl = root.querySelector('[data-role="upload-artist"]');
      const title = (titleEl ? titleEl.value : "").trim();
      const artist = (artistEl ? artistEl.value : "").trim();
      if (!pendingUploadFile) {
        showToast("Выберите аудиофайл");
        return;
      }
      if (!title || !artist) {
        showToast("Заполните название и исполнителя");
        return;
      }
      mutate({ upload: { ...getState().upload, title, artist, status: "loading", result: "" } });
      try {
        const track = await uploadTrack(pendingUploadFile, title, artist);
        pendingUploadFile = null;
        mutate({
          upload: {
            file: null,
            fileName: "",
            title: "",
            artist: "",
            status: "idle",
            result: `✅ «${escapeHtml(track.artist)} — ${escapeHtml(track.title)}» добавлен в библиотеку`,
          },
          libraryTotal: getState().libraryTotal + 1,
        });
        showToast("Трек загружен 🎵");
      } catch (error) {
        mutate({
          upload: {
            ...getState().upload,
            status: "idle",
            result: (error && error.message) || "Не удалось загрузить трек",
          },
        });
      }
    }

    // Enter в поиске — сохранить запрос в «Недавние», залогировать и убрать клавиатуру
    root.addEventListener("keydown", (event) => {
      if (event.key !== "Enter") return;
      const role = event.target.dataset ? event.target.dataset.role : null;
      if (role === "search-input") {
        const value = event.target.value.trim();
        if (value) {
          pushRecentSearch(value);
          commitSearchLog(value);
        }
        event.target.blur();
      }
      if (role === "mytracks-search" || role === "playlist-title") {
        if (role === "playlist-title") submitCreatePlaylist();
        event.target.blur();
      }
    });

    // Перемотка плеера: pointer-drag по всей зоне касания (тап + перетаскивание).
    // Делегируем на root — полоска перерисовывается при смене трека, но не во
    // время drag, поэтому захват переживает ре-рендеры. move/up слушаем на window,
    // чтобы палец мог уйти за пределы полоски и перемотка не срывалась.
    function seekFractionAt(track, clientX) {
      // Смена трека или тост посреди перетаскивания пересоздают полоску: у
      // оторванного узла ширина 0, и перемотка улетала в начало. Берём живую.
      if (!track.isConnected) track = document.querySelector('[data-action="seek"]') || track;
      const rect = track.getBoundingClientRect();
      if (!rect.width) return 0;
      return Math.min(1, Math.max(0, (clientX - rect.left) / rect.width));
    }

    function paintSeek(fraction) {
      const pct = `${fraction * 100}%`;
      const fill = document.getElementById("player-progress-fill");
      const thumb = document.getElementById("player-progress-thumb");
      const time = document.getElementById("player-time-current");
      if (fill) fill.style.width = pct;
      if (thumb) thumb.style.left = pct;
      const duration = getState().currentTrack?.duration;
      if (time && duration) time.textContent = formatDuration(fraction * duration);
    }

    root.addEventListener("pointerdown", (event) => {
      const track = event.target.closest('[data-action="seek"]');
      if (!track) return;
      event.preventDefault();
      isSeeking = true;
      track.classList.add("is-seeking");
      paintSeek(seekFractionAt(track, event.clientX));

      const onMove = (e) => paintSeek(seekFractionAt(track, e.clientX));
      const onUp = (e) => {
        seekToFraction(seekFractionAt(track, e.clientX));
        isSeeking = false;
        track.classList.remove("is-seeking");
        window.removeEventListener("pointermove", onMove);
        window.removeEventListener("pointerup", onUp);
        window.removeEventListener("pointercancel", onUp);
      };
      window.addEventListener("pointermove", onMove);
      window.addEventListener("pointerup", onUp);
      window.addEventListener("pointercancel", onUp);
    });

    // Свайп вниз закрывает плеер/шит, на вложенных страницах — шаг назад (ТЗ §3).
    let gestureStartY = null;
    let gestureStartX = null;
    let gestureScrollTop = 0;

    root.addEventListener(
      "touchstart",
      (event) => {
        const touch = event.touches[0];
        gestureStartY = touch.clientY;
        gestureStartX = touch.clientX;
        gestureScrollTop = document.scrollingElement.scrollTop;
      },
      { passive: true }
    );

    root.addEventListener("touchend", (event) => {
      if (gestureStartY == null) return;
      const touch = event.changedTouches[0];
      const dy = touch.clientY - gestureStartY;
      const dx = Math.abs(touch.clientX - gestureStartX);
      const startedNearTop = gestureStartY < window.innerHeight * 0.5;
      gestureStartY = null;
      gestureStartX = null;
      if (dy < 90 || dx > 70) return; // не выраженный свайп вниз

      const state = getState();
      if (state.sheetTrack) {
        closeSheet();
        return;
      }
      if (state.sortSheetOpen) {
        mutate({ sortSheetOpen: false });
        return;
      }
      if (state.playerOpen) {
        closePlayer();
        return;
      }
      if (!TAB_SCREENS.has(state.screen) && startedNearTop && gestureScrollTop <= 4) {
        goBack();
      }
    });

    // Пробел — play/pause (десктопная отладка)
    document.addEventListener("keydown", (event) => {
      if (event.code === "Space" && event.target.tagName !== "INPUT" && event.target.tagName !== "TEXTAREA") {
        event.preventDefault();
        togglePlay();
      }
    });

    render();
    boot();
    return {  };
  })();

})();

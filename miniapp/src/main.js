import {
  addToLibrary,
  createPaymentLink,
  formatDuration,
  getLibrary,
  getLibraryIds,
  getAlbums,
  getAlbumTracks,
  getArtists,
  getArtistTracks,
  getInstrumentals,
  getLyrics,
  getPlaylists,
  getPlaylistTracks,
  getPopularQueries,
  getPremiumStatus,
  getProfile,
  getTracks,
  login,
  logSearchQuery,
  createPlaylist,
  submitLyrics,
  removeFromLibrary,
  resolveAudioUrl,
  sendTrackToChat,
  telegramUser,
} from "./api.js";
import {
  closePlayer,
  closeSheet,
  getState,
  goBack,
  mutate,
  navigateTo,
  openPlayer,
  openSheet,
  playMix,
  playRecommended,
  playVibe,
  playNext,
  playPrev,
  playTrack,
  resetToTab,
  seekToFraction,
  showToast,
  subscribe,
  subscribeProgress,
  togglePlay,
  toggleShuffle,
} from "./state.js";
import { renderHeader } from "./components/header.js";
import { renderBottomNav } from "./components/bottomNav.js";
import { renderMiniPlayer } from "./components/miniPlayer.js";
import { renderPlayerScreen } from "./components/playerScreen.js";
import { renderTrackSheet } from "./components/trackSheet.js";
import { icon } from "./components/icons.js";
import { renderHome } from "./screens/home.js";
import { renderSearch, renderSearchResults } from "./screens/search.js";
import { renderLibrary } from "./screens/library.js";
import { renderMyTracks, renderMyTracksBody, myTracksList } from "./screens/mytracks.js";
import { renderProfile } from "./screens/profile.js";
import { renderSettings } from "./screens/settings.js";
import { renderRecommendations } from "./screens/recommendations.js";
import { renderRecent } from "./screens/recent.js";
import { renderArtists } from "./screens/artists.js";
import { renderDocs } from "./screens/docs.js";
import { renderAchievements } from "./screens/achievements.js";
import { renderLyrics } from "./screens/lyrics.js";
import { renderDownloads } from "./screens/downloads.js";
import { renderPlaylists } from "./screens/playlists.js";
import { renderAlbums } from "./screens/albums.js";
import { renderCollection } from "./screens/collection.js";
import { renderReferral } from "./screens/referral.js";
import { renderPremium } from "./screens/premium.js";
import { renderEqualizer } from "./screens/equalizer.js";
import { renderInterface } from "./screens/interface.js";
import { renderStorage } from "./screens/storage.js";
import {
  isOffline,
  offlineSupported,
  saveOffline,
  removeOffline,
  offlineTracks,
} from "./offline.js";
import {
  getRecentTracks,
  saveRecSettings,
  clearRecSettings,
  pushRecentSearch,
  clearRecentSearches,
  toggleFavoriteArtist,
  applyAccent,
  getUiSettings,
  saveUiSettings,
} from "./prefs.js";
import { applyEqualizer, currentGains, getEqSettings, saveEqSettings } from "./equalizer.js";
import { getTrackById } from "./api.js";

const root = document.getElementById("app");
const tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;

if (tg) {
  tg.ready();
  tg.expand();
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
  recommendations: renderRecommendations,
  equalizer: renderEqualizer,
  interface: renderInterface,
  storage: renderStorage,
  recent: renderRecent,
  artists: renderArtists,
  docs: renderDocs,
  achievements: renderAchievements,
  lyrics: renderLyrics,
  downloads: renderDownloads,
  playlists: renderPlaylists,
  albums: renderAlbums,
  collection: renderCollection,
  referral: renderReferral,
  premium: renderPremium,
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

function render() {
  const state = getState();

  if (state.bootStatus !== "ready") {
    root.innerHTML = renderBootScreen(state);
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
  root.innerHTML = `
    ${renderHeader(state)}
    <main class="screen">${screenRenderer(state)}</main>
    <div class="bottom-dock">
      ${renderMiniPlayer(state)}
      ${showNav ? renderBottomNav(state.screen) : ""}
    </div>
    ${renderPlayerScreen(state)}
    ${renderTrackSheet(state)}
    ${state.toast ? `<div class="toast">${state.toast}</div>` : ""}
  `;

  if (keepFocus) {
    const input = root.querySelector(`[data-role="${focusedRole}"]`);
    if (input) {
      input.focus();
      input.setSelectionRange(caret, caret);
    }
  }
}

subscribe(render);

// Прогресс — мимо полного рендера: правим только стили/текст существующих узлов.
subscribeProgress((current, duration) => {
  if (!duration) return;
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
  mutate({ bootStatus: "loading", bootError: "" });
  try {
    await login();
    const [catalogPage, libraryIds, premium, libraryPage] = await Promise.all([
      getTracks("", 1, CATALOG_PAGE_SIZE),
      getLibraryIds(),
      getPremiumStatus(),
      getLibrary(1),
    ]);
    mutate({
      bootStatus: "ready",
      user: telegramUser(),
      catalog: catalogPage.items,
      catalogTotal: catalogPage.total,
      libraryIds: new Set(libraryIds),
      libraryPageItems: libraryPage.items,
      libraryTotal: libraryPage.total,
      premium,
    });
    getPopularQueries()
      .then((queries) => mutate({ popularQueries: queries }))
      .catch(() => {});
  } catch (error) {
    mutate({
      bootStatus: "error",
      bootError: error && error.message ? error.message : "Не удалось загрузить данные",
    });
  }
}

let libraryPagesLoaded = 1;

async function loadMoreLibrary() {
  const next = libraryPagesLoaded + 1;
  const page = await getLibrary(next);
  libraryPagesLoaded = next;
  const state = getState();
  mutate({
    libraryPageItems: [...state.libraryPageItems, ...page.items],
    libraryTotal: page.total,
  });
}

async function loadProfile() {
  if (getState().profileStatus === "loading") return;
  mutate({ profileStatus: "loading" });
  try {
    mutate({ profile: await getProfile(), profileStatus: "ready" });
  } catch {
    mutate({ profileStatus: "error" });
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

function scheduleSearch(query) {
  const state = getState();
  state.searchQuery = query;
  clearTimeout(searchTimer);
  const seq = ++searchSeq;
  if (!query.trim()) {
    mutateSearch({ searchResults: [], searchTotal: 0, searchStatus: "idle" });
    return;
  }
  mutateSearch({ searchStatus: "loading" });
  searchTimer = setTimeout(async () => {
    try {
      const fetcher = getState().searchMode === "instrumentals" ? getInstrumentals : getTracks;
      const page = await fetcher(query.trim(), 1, 50);
      if (seq !== searchSeq) return; // пришёл более свежий запрос
      mutateSearch({ searchResults: page.items, searchTotal: page.total, searchStatus: "done" });
    } catch {
      if (seq !== searchSeq) return;
      mutateSearch({ searchResults: [], searchTotal: 0, searchStatus: "done" });
    }
  }, 300);
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
  logSearchQuery(value);
  scheduleSearch(value);
}

// «Мои треки»: ввод в поиске перерисовывает только тело списка (фокус живёт)
function refreshMyTracksBody() {
  const container = document.getElementById("mytracks-body");
  if (container) container.innerHTML = renderMyTracksBody(getState());
}

// «Скачать всё» (шит Моих треков, скрин VK): офлайн-кэш всей библиотеки — Premium.
async function downloadAllTracks() {
  mutate({ myTracksMenuOpen: false });
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
  const list = myTracksList(state).filter((t) => t.id > 0 && !isOffline(t.id));
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

async function handleToggleLibrary(trackId, fromSheet) {
  if (fromSheet) closeSheet();
  if (!trackId || trackId < 0) return; // минусы в библиотеку не добавляются
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

async function handlePayPremium() {
  try {
    const months = getState().premiumMonths || 1;
    const { confirmation_url: url } = await createPaymentLink(months);
    if (tg) tg.openLink(url);
    else window.open(url, "_blank");
  } catch {
    showToast("Оплата временно недоступна");
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
    (state.currentTrack && state.currentTrack.id === trackId ? state.currentTrack : null)
  );
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
      break;
    case "open-achievements":
      navigateTo("achievements");
      if (!getState().profile) loadProfile();
      break;
    case "open-referral":
      navigateTo("referral");
      if (!getState().profile) loadProfile();
      break;
    case "open-premium":
      navigateTo("premium");
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
      const shareUrl = `https://t.me/share/url?url=${encodeURIComponent(profile.referral.link)}&text=${encodeURIComponent("Слушай музыку в TG Music 🎧")}`;
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
    case "open-artist": {
      const name = el.dataset.artist;
      openCollection(name, "artist", () => getArtistTracks(name));
      break;
    }
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
    case "open-interface":
      navigateTo("interface");
      break;
    case "open-storage":
      navigateTo("storage");
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
    case "seek": {
      const rect = el.getBoundingClientRect();
      seekToFraction((event.clientX - rect.left) / rect.width);
      break;
    }
    case "download":
      event.stopPropagation();
      handleDownload(id);
      break;
    case "share": {
      const track = findTrack(id);
      if (track) {
        const shareUrl = `https://t.me/share/url?url=${encodeURIComponent(`https://t.me/tgram_music_bot?start=track_${track.id}`)}&text=${encodeURIComponent(`${track.artist} — ${track.title}`)}`;
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
      if (tg) tg.openTelegramLink("https://t.me/Mystadm");
      else window.open("https://t.me/Mystadm", "_blank");
      break;
    case "open-bot":
      if (tg) tg.openTelegramLink("https://t.me/tgram_music_bot");
      else window.open("https://t.me/tgram_music_bot", "_blank");
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
  if (event.target.dataset && event.target.dataset.role === "eq-band") {
    mutate({});
  }
});

// Enter в поиске — сохранить запрос в «Недавние», залогировать и убрать клавиатуру
root.addEventListener("keydown", (event) => {
  if (event.key !== "Enter") return;
  const role = event.target.dataset ? event.target.dataset.role : null;
  if (role === "search-input") {
    const value = event.target.value.trim();
    if (value) {
      pushRecentSearch(value);
      logSearchQuery(value);
    }
    event.target.blur();
  }
  if (role === "mytracks-search" || role === "playlist-title") {
    if (role === "playlist-title") submitCreatePlaylist();
    event.target.blur();
  }
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

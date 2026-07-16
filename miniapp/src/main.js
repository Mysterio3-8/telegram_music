import {
  addToLibrary,
  createPaymentLink,
  formatDuration,
  getLibrary,
  getLibraryIds,
  getAlbums,
  getAlbumTracks,
  getLyrics,
  getPlaylists,
  getPlaylistTracks,
  getPremiumStatus,
  getProfile,
  getTracks,
  login,
  submitLyrics,
  removeFromLibrary,
  resolveAudioUrl,
  telegramUser,
} from "./api.js";
import {
  closePlayer,
  closeSheet,
  getState,
  mutate,
  openPlayer,
  openSheet,
  playAll,
  playMix,
  playRecommended,
  playNext,
  playPrev,
  playTrack,
  seekToFraction,
  setScreen,
  showToast,
  subscribe,
  subscribeProgress,
  togglePlay,
  toggleShuffle,
  toggleTheme,
} from "./state.js";
import { renderHeader } from "./components/header.js";
import { renderBottomNav } from "./components/bottomNav.js";
import { renderMiniPlayer } from "./components/miniPlayer.js";
import { renderPlayerScreen } from "./components/playerScreen.js";
import { renderTrackSheet } from "./components/trackSheet.js";
import { renderHome } from "./screens/home.js";
import { renderSearch, renderSearchResults } from "./screens/search.js";
import { renderLibrary } from "./screens/library.js";
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
import { isOffline, saveOffline, removeOffline, offlineTracks } from "./offline.js";
import {
  getRecentTracks,
  saveRecSettings,
  clearRecSettings,
  pushRecentSearch,
  clearRecentSearches,
  toggleFavoriteArtist,
} from "./prefs.js";

const root = document.getElementById("app");
const tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;

document.documentElement.setAttribute("data-theme", getState().theme);
if (tg) {
  tg.ready();
  tg.expand();
}

const SCREENS = {
  home: renderHome,
  search: renderSearch,
  library: renderLibrary,
  profile: renderProfile,
  settings: renderSettings,
  recommendations: renderRecommendations,
  recent: renderRecent,
  artists: renderArtists,
  docs: renderDocs,
  achievements: renderAchievements,
  lyrics: renderLyrics,
  downloads: renderDownloads,
  playlists: renderPlaylists,
  albums: renderAlbums,
  collection: renderCollection,
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
  root.classList.toggle("is-playing", Boolean(state.currentTrack));

  const focused = document.activeElement;
  const wasSearchFocused = focused && focused.dataset && focused.dataset.role === "search-input";
  const caret = wasSearchFocused ? focused.selectionStart : null;

  root.innerHTML = `
    ${renderHeader(state)}
    <main class="screen">${screenRenderer(state)}</main>
    ${showNav ? renderBottomNav(state.screen) : ""}
    ${renderMiniPlayer(state)}
    ${renderPlayerScreen(state)}
    ${renderTrackSheet(state)}
    ${state.toast ? `<div class="toast">${state.toast}</div>` : ""}
  `;

  if (wasSearchFocused) {
    const input = root.querySelector('[data-role="search-input"]');
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

let lyricsReturn = "home"; // экран, куда вернуться с экрана текста

async function loadLyrics(track) {
  mutate({
    lyricsTrack: track,
    lyrics: null,
    lyricsStatus: "loading",
    lyricsEditing: false,
    screen: "lyrics",
  });
  try {
    const data = await getLyrics(track.id);
    mutate({ lyrics: data, lyricsStatus: "ready", lyricsEditing: !data.found });
  } catch {
    mutate({ lyrics: { found: false, text: null }, lyricsStatus: "ready", lyricsEditing: true });
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

let collectionReturn = "library"; // экран, куда вернуться из подборки

async function loadPlaylists() {
  mutate({ playlistsStatus: "loading", screen: "playlists" });
  try {
    mutate({ playlists: await getPlaylists(), playlistsStatus: "ready" });
  } catch {
    mutate({ playlistsStatus: "error" });
  }
}

async function loadAlbums() {
  mutate({ albumsStatus: "loading", screen: "albums" });
  try {
    mutate({ albums: await getAlbums(), albumsStatus: "ready" });
  } catch {
    mutate({ albumsStatus: "error" });
  }
}

async function openCollection(title, fetcher, from) {
  collectionReturn = from;
  mutate({
    collectionTitle: title,
    collectionTracks: [],
    collectionStatus: "loading",
    screen: "collection",
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
      const page = await getTracks(query.trim(), 1, 50);
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

// Запуск поиска по чипу (популярный/недавний запрос): подставляем в инпут,
// сохраняем в недавние и ищем.
function runSearch(query) {
  const value = (query || "").trim();
  if (!value) return;
  const input = root.querySelector('[data-role="search-input"]');
  if (input) input.value = value;
  pushRecentSearch(value);
  scheduleSearch(value);
}

function contextTracks(context) {
  const state = getState();
  if (context === "search") return state.searchResults;
  if (context === "library") return state.libraryPageItems;
  if (context === "recent") return getRecentTracks();
  if (context === "offline") return offlineTracks();
  if (context === "collection") return state.collectionTracks;
  return state.catalog;
}

async function handleToggleLibrary(trackId, fromSheet) {
  const state = getState();
  const inLibrary = state.libraryIds.has(trackId);
  // Оптимистично: интерфейс мгновенный, при ошибке откатываем
  const nextIds = new Set(state.libraryIds);
  if (inLibrary) nextIds.delete(trackId);
  else nextIds.add(trackId);
  mutate({ libraryIds: nextIds });
  try {
    if (inLibrary) {
      await removeFromLibrary(trackId);
      mutate({
        libraryPageItems: getState().libraryPageItems.filter((t) => t.id !== trackId),
        libraryTotal: Math.max(0, getState().libraryTotal - 1),
      });
    } else {
      await addToLibrary(trackId);
      showToast("Добавлено в библиотеку");
    }
  } catch {
    mutate({ libraryIds: state.libraryIds }); // откат
    showToast("Не получилось — попробуйте ещё раз");
  }
  if (fromSheet) closeSheet();
}

async function handlePayPremium() {
  try {
    const { confirmation_url: url } = await createPaymentLink();
    if (tg) tg.openLink(url);
    else window.open(url, "_blank");
  } catch {
    showToast("Оплата временно недоступна");
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

  switch (action) {
    case "retry-boot":
      boot();
      break;
    case "nav":
      setScreen(el.dataset.screen);
      break;
    case "open-settings":
      setScreen("settings");
      break;
    case "open-profile":
      setScreen("profile");
      loadProfile();
      break;
    case "open-achievements":
      setScreen("achievements");
      if (!getState().profile) loadProfile();
      break;
    case "invite-friend": {
      const profile = getState().profile;
      if (!profile) break;
      const shareUrl = `https://t.me/share/url?url=${encodeURIComponent(profile.referral.link)}&text=${encodeURIComponent("Слушай музыку в TG Music 🎧")}`;
      if (tg) tg.openTelegramLink(shareUrl);
      else window.open(shareUrl, "_blank");
      break;
    }
    case "theme-toggle":
      toggleTheme();
      break;
    case "play-all":
      playAll();
      break;
    case "play-mix": {
      const mix = el.dataset.mix;
      const msg = mix.startsWith("library") ? "Добавьте треки в библиотеку" : "В базе пока нет треков";
      playMix(mixTracks(mix), msg);
      break;
    }
    case "open-artists":
      setScreen("artists");
      break;
    case "open-doc":
      mutate({ docKey: el.dataset.doc, screen: "docs" });
      break;
    case "toggle-artist":
      toggleFavoriteArtist(el.dataset.artist);
      mutate({});
      break;
    case "soon":
      showToast("Появится в следующем обновлении");
      break;
    case "open-lyrics": {
      event.stopPropagation();
      const track = findTrack(id);
      if (!track) break;
      const current = getState().screen;
      lyricsReturn = TAB_SCREENS.has(current) ? current : "home";
      closeSheet();
      loadLyrics(track);
      break;
    }
    case "lyrics-back":
      setScreen(lyricsReturn);
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
      setScreen("downloads");
      break;
    case "play-recommended":
      playRecommended();
      break;
    case "open-playlists":
      loadPlaylists();
      break;
    case "open-albums":
      loadAlbums();
      break;
    case "open-curators":
      openCollection("Кураторы", async () => [], "library");
      break;
    case "open-playlist":
      openCollection(el.dataset.title || "Плейлист", () => getPlaylistTracks(id), "playlists");
      break;
    case "open-album":
      openCollection(el.dataset.name, () => getAlbumTracks(el.dataset.name), "albums");
      break;
    case "collection-back":
      setScreen(collectionReturn);
      break;
    case "collection-play":
      playMix(getState().collectionTracks, "Здесь пока пусто");
      break;
    case "open-recommendations":
      setScreen("recommendations");
      break;
    case "open-recent":
      setScreen("recent");
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
      setScreen("home");
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
    case "clear-recent-searches":
      clearRecentSearches();
      mutateSearch({});
      break;
    case "play-track": {
      const track = findTrack(id);
      if (!track) return;
      playTrack(track, contextTracks(el.dataset.context));
      openPlayer();
      break;
    }
    case "toggle-library":
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
    case "download": {
      const track = findTrack(id);
      const url = track ? resolveAudioUrl(track) : null;
      if (url) {
        const absolute = url.startsWith("http") ? url : location.origin + url;
        if (tg) tg.openLink(absolute);
        else window.open(absolute, "_blank");
      }
      closeSheet();
      break;
    }
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
    case "open-bot":
      if (tg) tg.openTelegramLink("https://t.me/tgram_music_bot");
      else window.open("https://t.me/tgram_music_bot", "_blank");
      break;
    default:
      break;
  }
});

root.addEventListener("input", (event) => {
  if (event.target.dataset && event.target.dataset.role === "search-input") {
    scheduleSearch(event.target.value);
  }
});

// Enter в поиске — сохранить запрос в «Недавние» и убрать клавиатуру
root.addEventListener("keydown", (event) => {
  if (event.key !== "Enter") return;
  if (event.target.dataset && event.target.dataset.role === "search-input") {
    const value = event.target.value.trim();
    if (value) pushRecentSearch(value);
    event.target.blur();
  }
});

// Свайп вниз закрывает открытую страницу/плеер/шит (ТЗ: закрытие жестом).
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
  if (state.playerOpen) {
    closePlayer();
    return;
  }
  if (!TAB_SCREENS.has(state.screen) && startedNearTop && gestureScrollTop <= 4) {
    setScreen("home");
  }
});

// Пробел — play/pause (десктопная отладка)
document.addEventListener("keydown", (event) => {
  if (event.code === "Space" && event.target.tagName !== "INPUT") {
    event.preventDefault();
    togglePlay();
  }
});

render();
boot();

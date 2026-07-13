import {
  addToLibrary,
  createPaymentLink,
  formatDuration,
  getLibrary,
  getLibraryIds,
  getPremiumStatus,
  getTracks,
  login,
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
  if (fill) fill.style.width = `${fraction * 100}%`;
  if (thumb) thumb.style.left = `${fraction * 100}%`;
  if (time) time.textContent = formatDuration(current);
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

function contextTracks(context) {
  const state = getState();
  if (context === "search") return state.searchResults;
  if (context === "library") return state.libraryPageItems;
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
    (state.currentTrack && state.currentTrack.id === trackId ? state.currentTrack : null)
  );
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
      break;
    case "theme-toggle":
      toggleTheme();
      break;
    case "play-all":
      playAll();
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

// Пробел — play/pause (десктопная отладка)
document.addEventListener("keydown", (event) => {
  if (event.code === "Space" && event.target.tagName !== "INPUT") {
    event.preventDefault();
    togglePlay();
  }
});

render();
boot();

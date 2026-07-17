import { resolveAudioUrl, shuffle, recordListen, getMix } from "./api.js";
import { pushRecentTrack, getRecSettings } from "./prefs.js";
import { isOffline, offlineBlobUrl } from "./offline.js";

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
  queue: [],
  queueIndex: -1,
  currentTrack: null,
  isPlaying: false,
  shuffleMode: true,
  playerOpen: false,
  sheetTrack: null,
  toast: "",
  recDraft: getRecSettings(), // редактируемый черновик настроек рекомендаций
  subDismissed: false, // карточка подписки скрыта на эту сессию
  docKey: "about", // активный статический документ (faq/privacy/license/about)
  profile: null, // геймификация: ранг, приглашённые, достижения (грузится при открытии профиля)
  profileStatus: "idle", // idle | loading | ready | error
  lyricsTrack: null, // трек, для которого открыт экран текста
  lyrics: null, // {text, source, found}
  lyricsStatus: "idle", // idle | loading | ready | error
  lyricsEditing: false,
  playlists: [],
  playlistsStatus: "idle",
  albums: [],
  albumsStatus: "idle",
  curators: [],
  curatorsStatus: "idle",
  searchMode: "tracks", // tracks | instrumentals — вкладки в поиске
  collectionTitle: "",
  collectionTracks: [],
  collectionStatus: "idle",
};

const structureListeners = new Set();
const progressListeners = new Set();

export const audio = new Audio();
audio.preload = "auto";

function notify() {
  structureListeners.forEach((fn) => fn(state));
}

export function subscribe(fn) {
  structureListeners.add(fn);
  return () => structureListeners.delete(fn);
}

export function subscribeProgress(fn) {
  progressListeners.add(fn);
  return () => progressListeners.delete(fn);
}

audio.addEventListener("timeupdate", () => {
  progressListeners.forEach((fn) => fn(audio.currentTime, audio.duration || 0));
});

audio.addEventListener("ended", () => {
  playNext();
});

audio.addEventListener("play", () => {
  if (!state.isPlaying) {
    state.isPlaying = true;
    notify();
  }
});

audio.addEventListener("pause", () => {
  // pause в конце трека прилетает перед ended — не дёргаем структуру зря
  if (state.isPlaying && !audio.ended) {
    state.isPlaying = false;
    notify();
  }
});

let consecutiveErrors = 0;

audio.addEventListener("error", () => {
  if (!state.currentTrack) return;
  consecutiveErrors += 1;
  if (consecutiveErrors >= Math.max(3, state.queue.length)) {
    // вся очередь битая — не зацикливаемся на переборе
    state.isPlaying = false;
    showToast("Треки недоступны — попробуйте позже");
    notify();
    return;
  }
  showToast("Не удалось загрузить трек — пропускаю");
  playNext();
});

audio.addEventListener("playing", () => {
  consecutiveErrors = 0;
});

export function getState() {
  return state;
}

export function mutate(patch) {
  Object.assign(state, patch);
  notify();
}

export function setScreen(screen) {
  state.screen = screen;
  notify();
}

let toastTimer = null;

export function showToast(text) {
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
  navigator.mediaSession.metadata = new MediaMetadata({
    title: track.title,
    artist: track.artist,
  });
  navigator.mediaSession.setActionHandler("nexttrack", playNext);
  navigator.mediaSession.setActionHandler("previoustrack", playPrev);
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

function setAudioSource(track) {
  const playNetwork = () => {
    const url = resolveAudioUrl(track);
    if (!url) {
      showToast("У трека нет аудио");
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

function startTrack(index) {
  const track = state.queue[index];
  if (!track) return;
  state.queueIndex = index;
  state.currentTrack = track;
  state.isPlaying = true;
  pushRecentTrack(track);
  if (typeof track.id === "number" && track.id > 0) recordListen(track.id); // минусы (id<0) не пишем
  setAudioSource(track);
  updateMediaSession(track);
  notify();
}

// Единая точка запуска очереди для всех разделов (Player Engine, ТЗ §7-8).
export function playTrack(track, contextList) {
  const source = contextList && contextList.length ? contextList : [track];
  if (state.shuffleMode) {
    state.queue = [track, ...shuffle(source.filter((t) => t.id !== track.id))];
    startTrack(0);
  } else {
    state.queue = source;
    startTrack(Math.max(0, source.findIndex((t) => t.id === track.id)));
  }
}

export function playAll() {
  playMix(state.catalog, "В базе пока нет треков");
}

// Персональный микс под сохранённые настройки рекомендаций (настроение/тип/язык).
export async function playRecommended() {
  showToast("Собираю рекомендации…");
  try {
    const tracks = await getMix(getRecSettings());
    playMix(tracks, "Пока нечего рекомендовать");
  } catch {
    showToast("Не удалось собрать микс");
  }
}

// Запуск произвольного микса (варианты swipe-hero: вся база / любимые / рекомендации).
export function playMix(list, emptyMessage = "Здесь пока нет треков") {
  if (!list || !list.length) {
    showToast(emptyMessage);
    return;
  }
  state.queue = shuffle(list);
  startTrack(0);
  state.playerOpen = true;
  notify();
}

export function togglePlay() {
  if (!state.currentTrack) return;
  if (audio.paused) {
    audio.play().catch(() => {});
  } else {
    audio.pause();
  }
}

export function playNext() {
  if (!state.queue.length) return;
  let next = state.queueIndex + 1;
  if (next >= state.queue.length) {
    // очередь закончилась — новая случайная из того же пула (ТЗ §5)
    state.queue = shuffle(state.queue);
    next = 0;
  }
  startTrack(next);
}

export function playPrev() {
  if (!state.queue.length) return;
  if (audio.currentTime > 3) {
    audio.currentTime = 0;
    return;
  }
  startTrack(Math.max(0, state.queueIndex - 1));
}

export function seekToFraction(fraction) {
  if (!audio.duration) return;
  audio.currentTime = Math.min(audio.duration - 0.1, Math.max(0, fraction * audio.duration));
}

export function toggleShuffle() {
  state.shuffleMode = !state.shuffleMode;
  notify();
}

export function openPlayer() {
  state.playerOpen = true;
  notify();
}

export function closePlayer() {
  state.playerOpen = false;
  notify();
}

export function openSheet(track) {
  state.sheetTrack = track;
  notify();
}

export function closeSheet() {
  state.sheetTrack = null;
  notify();
}

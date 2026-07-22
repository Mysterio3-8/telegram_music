import {
  resolveAudioUrl,
  shuffle,
  recordListen,
  getMix,
  getTrackById,
  getTracks,
} from "./api.js";
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
  collectionStatus: "idle",
  collectionType: "playlist", // playlist | album | artist — влияет на шапку экрана
  popularQueries: [], // реальные популярные запросы с сервера (ТЗ §11)
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
};

const structureListeners = new Set();
const progressListeners = new Set();

export const audio = new Audio();
audio.preload = "auto";
// Для эквалайзера (Web Audio createMediaElementSource) источник должен быть
// CORS-чистым; на same-origin прода атрибут безвреден
audio.crossOrigin = "anonymous";

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
  const track = state.currentTrack;
  if (!track) return;
  consecutiveErrors += 1;
  if (consecutiveErrors >= Math.max(3, state.queue.length)) {
    // вся очередь битая — не зацикливаемся на переборе
    state.isPlaying = false;
    showToast("Треки недоступны — попробуйте позже");
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

export function getState() {
  return state;
}

export function mutate(patch) {
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

export function navigateTo(screen, patch = {}) {
  navStack[navStack.length - 1].scroll = readScrollTop();
  navStack.push({ screen, patch, scroll: 0 });
  Object.assign(state, patch);
  state.screen = screen;
  notify();
  applyScrollTop(0);
}

export function goBack() {
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
export function resetToTab(tab) {
  navStack.length = 1;
  navStack[0] = { screen: tab, patch: {}, scroll: 0 };
  state.screen = tab;
  notify();
  applyScrollTop(0);
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

// Свежая подписанная ссылка по id: для треков из «Недавних» (audio_url не хранится)
// и при ошибке воспроизведения (кэшированная ссылка старше 6 часов → 403).
async function refreshAndPlay(track) {
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

// Mood-микс с карточки «Какой сейчас вайб?» на главной (тот же /mix, что «Настроить»).
export async function playVibe(mood) {
  showToast("Собираю подборку…");
  try {
    const tracks = await getMix({ mood });
    playMix(tracks, "Пока нет треков под это настроение");
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

export function toggleRepeat() {
  state.repeatMode = !state.repeatMode;
  audio.loop = state.repeatMode; // loop=true — ended не стреляет, трек крутится сам
  notify();
}

// Прыжок на трек прямо из панели «Очередь» (скрины VK)
export function playQueueIndex(index) {
  if (index < 0 || index >= state.queue.length) return;
  startTrack(index);
}

// «Микс по треку»: очередь = сам трек + его исполнитель + общий микс
export async function playTrackMix(track) {
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

export function setSleepTimer(minutes) {
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

export function openPlayer() {
  state.playerOpen = true;
  notify();
}

export function closePlayer() {
  state.playerOpen = false;
  state.queueOpen = false;
  state.playerSettingsOpen = false;
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

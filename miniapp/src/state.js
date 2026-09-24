import {
  resolveAudioUrl,
  shuffle,
  recordListen,
  recordListenSeconds,
  getMix,
  getInfinityMix,
  getTrackById,
  getTracks,
  liveStreamUrl,
  queueLiveFetch,
} from "./api.js";
import { pushRecentTrack, getRecSettings } from "./prefs.js";
import { isOffline, offlineBlobUrl } from "./offline.js";
import { trackClient } from "./analytics.js";

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
  infinityMix: false, // очередь собрана Infinity Mix — её доливают, а не зацикливают
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
    return;
  }
  // Уходим из приложения — досчитываем последний трек, иначе он не попал бы в
  // статистику вовсе: смены трека, на которой мы обычно отчитываемся, не будет.
  if (document.visibilityState === "hidden") reportListened();
});

window.addEventListener("pagehide", () => reportListened());

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
    // Раньше здесь было «Восстанавливаем эти треки — попробуйте через минуту».
    // Владелец 22.09: «такого вообще не должно быть, и надписи этой не должно
    // быть вообще». Сервер теперь дотягивает трек прямо в запросе, а четыре
    // промаха подряд — это сеть, а не каталог: молча останавливаемся.
    state.isPlaying = false;
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
  playNext(); // молча: человек не должен читать про наши промахи
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

// Значения полей экрана на момент ухода с него. 🔴 Без этого «Назад» показывал
// вечную загрузку: в стеке лежал patch, с которым экран ОТКРЫВАЛИ
// (`{playlistsStatus:"loading", collectionTracks: []}`), и возврат честно
// восстанавливал именно его — спиннер поверх стёртых данных, и обновить их было
// некому. Жалоба владельца 22.09: «бесконечная загрузка страницы когда жмёшь
// назад». Теперь запоминаем то, чем экран стал, а не то, с чего начинался.
function snapshotOf(patch) {
  const snapshot = {};
  for (const key of Object.keys(patch || {})) snapshot[key] = state[key];
  return snapshot;
}

export function navigateTo(screen, patch = {}) {
  trackClient("screen_view", { props: { screen } });
  const current = navStack[navStack.length - 1];
  current.scroll = readScrollTop();
  current.snapshot = snapshotOf(current.patch);
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
  Object.assign(state, top.snapshot || top.patch);
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
    playNext(); // поток источника не отдался — молча идём дальше
    return;
  }
  try {
    const fresh = await getTrackById(track.id);
    if (state.currentTrack !== track) return; // трек сменился, пока ходили за ссылкой
    if (!fresh.audio_url) {
      playNext();
      return;
    }
    track.audio_url = fresh.audio_url;
    playFrom(resolveAudioUrl(track), track);
  } catch {
    if (state.currentTrack !== track) return;
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

// Сколько предыдущий трек реально звучал — отправляем при каждой смене трека.
function reportListened() {
  const previous = state.currentTrack;
  if (!previous || typeof previous.id !== "number" || previous.id <= 0) return;
  const played = Math.min(audio.currentTime || 0, audio.duration || previous.duration || 0);
  if (played >= 5) recordListenSeconds(previous.id, played);
}

function startTrack(index) {
  const track = state.queue[index];
  if (!track) return;
  reportListened();
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
export function playTrack(track, contextList) {
  state.infinityMix = false;
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

// ---------- Infinity Mix: бесконечная лента без повторов ----------
// Владелец 22.09: «надо чтобы рандомные треки, абсолютно рандомные, даже
// которых нет в базе, без повторов». Поэтому лента не кончается: когда до
// конца очереди остаётся INFINITY_REFILL_AT треков, фоном докладываем
// следующую порцию. Сервер сам помнит показанное неделю и не повторяется.

const INFINITY_REFILL_AT = 5;
let infinityLoading = false;

function mixItemToTrack(item) {
  if (item.track_id) {
    return {
      id: item.track_id,
      title: item.title,
      artist: item.artist,
      duration: item.duration,
      cover_url: item.cover_url,
      audio_url: item.audio_url || null,
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

export async function playInfinityMix() {
  if (infinityLoading) return;
  infinityLoading = true;
  showToast("Собираю Infinity Mix…");
  try {
    const data = await getInfinityMix({ first: true });
    const list = (data.items || []).map(mixItemToTrack);
    if (!list.length) {
      showToast("Не удалось собрать микс");
      return;
    }
    state.infinityMix = true;
    state.queue = list; // порядок уже собран сервером: каталог первым, он играет сразу
    startTrack(0);
    state.playerOpen = true;
    notify();
  } catch {
    showToast("Не удалось собрать микс");
  } finally {
    infinityLoading = false;
  }
  refillInfinityMix(); // догружаем живую часть, пока играет первый трек
}

// Докладываем ленту молча — человек не должен видеть ни спиннера, ни паузы.
async function refillInfinityMix() {
  if (infinityLoading || !state.infinityMix) return;
  infinityLoading = true;
  try {
    const data = await getInfinityMix();
    const known = new Set(state.queue.map((t) => String(t.id)));
    const fresh = (data.items || [])
      .map(mixItemToTrack)
      .filter((t) => !known.has(String(t.id)));
    if (fresh.length) {
      state.queue = state.queue.concat(fresh);
      notify();
    }
  } catch {
    // Сеть отвалилась — лента доиграет то, что уже в очереди
  } finally {
    infinityLoading = false;
  }
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
  state.infinityMix = false;
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
  if (state.infinityMix) {
    // Лента бесконечная: доливаем заранее, чтобы стык был неслышным
    if (state.queue.length - next <= INFINITY_REFILL_AT) refillInfinityMix();
    if (next >= state.queue.length) {
      refillInfinityMix().then(() => {
        if (!state.infinityMix) return;
        if (next < state.queue.length) {
          startTrack(next);
          return;
        }
        // Источник ничего нового не дал (сеть, повторы) — лучше перемешать то,
        // что есть, чем оборвать музыку тишиной.
        state.queue = shuffle(state.queue);
        startTrack(0);
      });
      return;
    }
  } else if (next >= state.queue.length) {
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

// «Добавить в очередь» (референс): трек в конец очереди. Если очереди нет — играем сразу.
export function addToQueue(track) {
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
export function playNextInQueue(track) {
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

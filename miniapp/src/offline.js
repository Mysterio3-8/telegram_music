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

export function offlineSupported() {
  return supported;
}

export function offlineTracks() {
  return readIndex();
}

export function isOffline(trackId) {
  return readIndex().some((t) => t.id === trackId);
}

export async function saveOffline(track, absoluteAudioUrl) {
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

export async function removeOffline(trackId) {
  if (supported) {
    const cache = await caches.open(CACHE_NAME);
    await cache.delete(cacheKey(trackId));
  }
  writeIndex(readIndex().filter((t) => t.id !== trackId));
}

// Blob-URL закэшированного трека для мгновенного воспроизведения; null — нет в кэше.
export async function offlineBlobUrl(trackId) {
  if (!supported) return null;
  const cache = await caches.open(CACHE_NAME);
  const response = await cache.match(cacheKey(trackId));
  if (!response) return null;
  const blob = await response.blob();
  return URL.createObjectURL(blob);
}

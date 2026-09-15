import { sendAnalyticsEvents } from "./api.js";

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

export function trackClient(name, { trackId = null, props = null } = {}) {
  queue.push({ name, track_id: trackId, props });
  if (queue.length > MAX_QUEUE) queue.splice(0, queue.length - MAX_QUEUE);
  if (queue.length >= MAX_BATCH) {
    flushAnalytics();
  } else if (!timer) {
    timer = setTimeout(flushAnalytics, FLUSH_MS);
  }
}

export function flushAnalytics() {
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

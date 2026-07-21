// Эквалайзер (скрины VK в копи/): 7 полос Web Audio поверх <audio> плеера.
// Граф строится лениво при первом включении — если AudioContext недоступен
// (старый webview), плеер продолжает играть без эквалайзера.

import { audio } from "./state.js";

export const EQ_FREQS = [50, 100, 200, 400, 1000, 2500, 15000];
export const EQ_MIN_DB = -12;
export const EQ_MAX_DB = 12;

const EQ_KEY = "tgmusic-equalizer";

// Пресеты как в VK: имя → усиление (дБ) по 7 полосам
export const EQ_PRESETS = [
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

export function getEqSettings() {
  const fallback = { enabled: false, preset: "flat", custom: [0, 0, 0, 0, 0, 0, 0] };
  try {
    const saved = JSON.parse(localStorage.getItem(EQ_KEY) || "{}");
    return { ...fallback, ...saved };
  } catch {
    return fallback;
  }
}

export function saveEqSettings(settings) {
  try {
    localStorage.setItem(EQ_KEY, JSON.stringify(settings));
  } catch {
    // приватный режим — эквалайзер поживёт до перезапуска
  }
}

export function currentGains(settings = getEqSettings()) {
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

export function eqSupported() {
  return !graphFailed && Boolean(window.AudioContext || window.webkitAudioContext);
}

// Применить текущие настройки к графу. Выключен — все полосы в 0 (прозрачно).
export function applyEqualizer() {
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

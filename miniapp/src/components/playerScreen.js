import { icon } from "./icons.js";
import { renderCover } from "./cover.js";
import { escapeHtml } from "./trackRow.js";
import { formatDuration } from "../api.js";

const QUEUE_WINDOW = 120; // окно строк вокруг текущего трека — не рисуем тысячи узлов

// Экран плеера по референсу VK Music (ТЗ §7): обложка, название с «+»/«…»,
// ряд чипов Скачать/Текст, прогресс, контролы разумного размера.
// Прогресс-узлы имеют id и обновляются напрямую из subscribeProgress —
// компонент перерисовывается только при смене трека/состояния.
export function renderPlayerScreen(state) {
  const { currentTrack, isPlaying, shuffleMode } = state;
  if (!state.playerOpen || !currentTrack) return "";

  const isInstrumental = currentTrack.id < 0;
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

import { icon } from "./icons.js";
import { renderCover } from "./cover.js";
import { escapeHtml } from "./trackRow.js";
import { formatDuration } from "../api.js";

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
      <div class="player-chips">
        <button class="player-chip" data-action="download" data-id="${currentTrack.id}">${icon("download")} Скачать</button>
        <button class="player-chip" data-action="open-lyrics" data-id="${currentTrack.id}">${icon("lyrics")} Текст</button>
        <button class="player-chip" data-action="share" data-id="${currentTrack.id}">${icon("share")} Поделиться</button>
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
          <button class="player-controls__side" data-action="close-player" aria-label="Свернуть">${icon("chevron-down")}</button>
        </div>
      </div>
    </div>
  `;
}

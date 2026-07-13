import { icon } from "./icons.js";
import { renderCover } from "./cover.js";
import { escapeHtml } from "./trackRow.js";
import { formatDuration } from "../api.js";

// Прогресс-узлы имеют id и обновляются напрямую из subscribeProgress —
// этот компонент перерисовывается только при смене трека/состояния.
export function renderPlayerScreen(state) {
  const { currentTrack, isPlaying, shuffleMode } = state;
  if (!state.playerOpen || !currentTrack) return "";

  const inLibrary = state.libraryIds.has(currentTrack.id);

  return `
    <div class="player-overlay">
      <div class="player-overlay__inner">
        <div class="player-topbar">
          <button class="icon-btn" data-action="close-player" aria-label="Свернуть">${icon("chevron-down")}</button>
          <span class="player-topbar__label">Сейчас играет</span>
          <button class="icon-btn" data-action="open-sheet" data-id="${currentTrack.id}" aria-label="Ещё">${icon("more")}</button>
        </div>

        ${renderCover(currentTrack, "player-art")}

        <div class="player-meta">
          <div class="player-meta__title">${escapeHtml(currentTrack.title)}</div>
          <div class="player-meta__artist">${escapeHtml(currentTrack.artist)}</div>
        </div>

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
          <button class="player-controls__side${inLibrary ? " is-active" : ""}" data-action="toggle-library" data-id="${currentTrack.id}" aria-label="В библиотеку">${icon(inLibrary ? "check" : "plus")}</button>
        </div>
      </div>
    </div>
  `;
}

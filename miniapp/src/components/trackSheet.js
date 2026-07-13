import { icon } from "./icons.js";
import { renderCover } from "./cover.js";
import { escapeHtml } from "./trackRow.js";
import { formatDuration } from "../api.js";

export function renderTrackSheet(state) {
  const track = state.sheetTrack;
  if (!track) return "";
  const inLibrary = state.libraryIds.has(track.id);

  return `
    <div class="sheet-overlay" data-action="close-sheet">
      <div class="sheet" data-action="noop">
        <div class="sheet__handle"></div>
        <div class="sheet__track">
          ${renderCover(track)}
          <div class="track-info">
            <div class="track-title">${escapeHtml(track.title)}</div>
            <div class="track-artist">${escapeHtml(track.artist)} · ${formatDuration(track.duration)}</div>
          </div>
        </div>
        <button class="sheet-item" data-action="toggle-library" data-id="${track.id}" data-from-sheet="1">
          ${icon(inLibrary ? "check" : "plus")}
          ${inLibrary ? "Убрать из библиотеки" : "Добавить в библиотеку"}
        </button>
        <button class="sheet-item" data-action="download" data-id="${track.id}">
          ${icon("download")} Скачать
        </button>
        <button class="sheet-item" data-action="share" data-id="${track.id}">
          ${icon("share")} Поделиться
        </button>
        <button class="sheet-item is-danger" data-action="close-sheet">
          ${icon("close")} Закрыть
        </button>
      </div>
    </div>
  `;
}

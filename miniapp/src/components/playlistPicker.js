import { icon } from "./icons.js";
import { escapeHtml } from "./trackRow.js";

// Шит «Добавить в плейлист» (референс): создать новый + список существующих.
// state.playlistPickerTrack — id трека, который добавляем.

export function renderPlaylistPicker(state) {
  if (state.playlistPickerTrack == null) return "";
  const playlists = state.playlists || [];

  const list = playlists.length
    ? playlists
        .map(
          (p) => `
            <button class="sheet-item" data-action="picker-add" data-playlist="${p.id}">
              ${icon("playlist")} ${escapeHtml(p.title)}
              <span class="sheet-item__count">${p.track_count ?? ""}</span>
            </button>
          `
        )
        .join("")
    : '<div class="empty-state">У вас пока нет плейлистов</div>';

  return `
    <div class="sheet-overlay" data-action="close-playlist-picker">
      <div class="sheet" data-action="noop">
        <div class="sheet__handle"></div>
        <div class="sheet__title">Добавить в плейлист</div>
        <button class="sheet-item is-accent" data-action="picker-create">
          ${icon("plus")} Создать новый плейлист
        </button>
        ${list}
        <button class="sheet-item is-danger" data-action="close-playlist-picker">
          ${icon("close")} Закрыть
        </button>
      </div>
    </div>
  `;
}

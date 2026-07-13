import { icon } from "./icons.js";
import { renderCover } from "./cover.js";
import { formatDuration } from "../api.js";

// Один ряд трека — переиспользуется на Главной/Поиске/Библиотеке.
export function renderTrackRow(track, { context, inLibrary = false, playing = false } = {}) {
  return `
    <div class="track-row${playing ? " is-playing" : ""}" data-action="play-track" data-id="${track.id}" data-context="${context}">
      ${renderCover(track)}
      <div class="track-info">
        <div class="track-title">${escapeHtml(track.title)}</div>
        <div class="track-artist">${escapeHtml(track.artist)} · ${formatDuration(track.duration)}</div>
      </div>
      <div class="track-actions">
        <button class="icon-btn${inLibrary ? " is-added" : ""}" data-action="toggle-library" data-id="${track.id}" aria-label="В библиотеку">
          ${icon(inLibrary ? "check" : "plus")}
        </button>
        <button class="icon-btn" data-action="open-sheet" data-id="${track.id}" aria-label="Ещё">${icon("more")}</button>
      </div>
    </div>
  `;
}

export function renderTrackList(tracks, { context, state } = {}) {
  if (!tracks.length) return "";
  const currentId = state.currentTrack ? state.currentTrack.id : null;
  return tracks
    .map((t) =>
      renderTrackRow(t, {
        context,
        inLibrary: state.libraryIds.has(t.id),
        playing: t.id === currentId,
      })
    )
    .join("");
}

export function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

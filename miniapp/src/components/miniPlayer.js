import { icon } from "./icons.js";
import { renderCover } from "./cover.js";
import { escapeHtml } from "./trackRow.js";

export function renderMiniPlayer(state) {
  const { currentTrack, isPlaying, playerOpen } = state;
  if (!currentTrack || playerOpen) return "";

  return `
    <div class="mini-player">
      <div class="mini-player__inner" data-action="open-player">
        ${renderCover(currentTrack, "mini-player__cover")}
        <div class="mini-player__info">
          <div class="mini-player__title">${escapeHtml(currentTrack.title)}</div>
          <div class="mini-player__artist">${escapeHtml(currentTrack.artist)}</div>
        </div>
        <button class="mini-player__play" data-action="toggle-play" data-stop="1" aria-label="Play/Pause">
          ${icon(isPlaying ? "pause" : "play")}
        </button>
        <div class="mini-player__progress"><div class="mini-player__progress-fill" id="mini-progress-fill"></div></div>
      </div>
    </div>
  `;
}

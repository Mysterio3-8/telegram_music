import { icon } from "../components/icons.js";
import { renderTrackList } from "../components/trackRow.js";
import { getRecentTracks } from "../prefs.js";

export function renderRecent(state) {
  const tracks = getRecentTracks();

  return `
    <div class="page-head" data-role="page-head">
      <button class="icon-btn" data-action="nav" data-screen="home" aria-label="Назад">${icon("back")}</button>
      <span>Недавно прослушанные</span>
    </div>

    ${
      tracks.length
        ? `<div class="card home-track-card">${renderTrackList(tracks, { context: "recent", state })}</div>`
        : '<div class="empty-state">Здесь появятся треки, которые вы слушали.</div>'
    }
  `;
}

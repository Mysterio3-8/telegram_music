import { icon } from "../components/icons.js";
import { escapeHtml } from "../components/trackRow.js";

export function renderPlaylists(state) {
  const head = `
    <div class="page-head" data-role="page-head">
      <button class="icon-btn" data-action="nav" data-screen="library" aria-label="Назад">${icon("back")}</button>
      <span>Плейлисты</span>
    </div>
  `;

  if (state.playlistsStatus === "loading") {
    return `${head}<div class="empty-state">Загружаю…</div>`;
  }

  const playlists = state.playlists || [];
  if (!playlists.length) {
    return `${head}<div class="empty-state">Плейлистов пока нет.<br />Создайте их в боте — они появятся здесь.</div>`;
  }

  const rows = playlists
    .map(
      (p) => `
        <button class="quick-tile" data-action="open-playlist" data-id="${p.id}" data-title="${escapeHtml(p.title)}">
          <span class="quick-tile__icon">${icon("playlist")}</span>
          <span class="quick-tile__text">
            <span class="quick-tile__title">${escapeHtml(p.title)}</span>
            <span class="quick-tile__sub">${p.track_count} треков</span>
          </span>
        </button>
      `
    )
    .join("");

  return `${head}<div class="quick-access">${rows}</div>`;
}

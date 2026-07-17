import { icon } from "../components/icons.js";
import { escapeHtml } from "../components/trackRow.js";

export function renderAlbums(state) {
  const head = `
    <div class="page-head" data-role="page-head">
      <button class="icon-btn" data-action="back" aria-label="Назад">${icon("back")}</button>
      <span>Альбомы</span>
    </div>
  `;

  if (state.albumsStatus === "loading") {
    return `${head}<div class="empty-state">Загружаю…</div>`;
  }

  const albums = state.albums || [];
  if (!albums.length) {
    return `${head}<div class="empty-state">Альбомов пока нет — у треков не заполнено поле альбома.</div>`;
  }

  const rows = albums
    .map(
      (a) => `
        <button class="quick-tile" data-action="open-album" data-name="${escapeHtml(a.name)}">
          <span class="quick-tile__icon">${icon("album")}</span>
          <span class="quick-tile__text">
            <span class="quick-tile__title">${escapeHtml(a.name)}</span>
            <span class="quick-tile__sub">${a.track_count} треков</span>
          </span>
        </button>
      `
    )
    .join("");

  return `${head}<div class="quick-access">${rows}</div>`;
}

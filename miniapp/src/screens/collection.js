import { icon } from "../components/icons.js";
import { renderTrackList, escapeHtml } from "../components/trackRow.js";

// Универсальный экран содержимого плейлиста/альбома: заголовок + «слушать» + список.
export function renderCollection(state) {
  const head = `
    <div class="page-head" data-role="page-head">
      <button class="icon-btn" data-action="collection-back" aria-label="Назад">${icon("back")}</button>
      <span>${escapeHtml(state.collectionTitle || "Подборка")}</span>
    </div>
  `;

  if (state.collectionStatus === "loading") {
    return `${head}<div class="empty-state">Загружаю…</div>`;
  }

  const tracks = state.collectionTracks || [];
  if (!tracks.length) {
    return `${head}<div class="empty-state">Здесь пока пусто.</div>`;
  }

  return `
    ${head}
    <button class="btn btn--primary btn--block" data-action="collection-play" style="margin-bottom:14px">
      ${icon("play")} Слушать (${tracks.length})
    </button>
    <div class="card home-track-card">${renderTrackList(tracks, { context: "collection", state })}</div>
  `;
}

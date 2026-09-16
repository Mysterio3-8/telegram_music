import { icon } from "../components/icons.js";
import { renderTrackList, escapeHtml } from "../components/trackRow.js";
import { renderCover } from "../components/cover.js";

// Страница плейлиста/альбома/исполнителя по референсу VK Music (ТЗ §6):
// крупная обложка, название, счётчик и длительность, кнопки Слушать/Перемешать.

const TYPE_LABEL = { playlist: "Плейлист", album: "Альбом", artist: "Исполнитель", genre: "Жанр" };

function totalDuration(tracks) {
  const total = tracks.reduce((sum, t) => sum + (t.duration || 0), 0);
  const minutes = Math.round(total / 60);
  if (minutes < 60) return `${minutes} мин`;
  return `${Math.floor(minutes / 60)} ч ${minutes % 60} мин`;
}

function formatDuration(seconds) {
  const s = Math.max(0, Math.round(seconds || 0));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

// Живые треки альбома (16.09): играют по номеру, а не по id — у них id «live:…»
function renderLiveRows(items) {
  return items
    .map(
      (item, i) => `
        <div class="track-row" data-action="play-album-live" data-index="${i}">
          ${renderCover({ ...item, id: item.ref })}
          <div class="track-info">
            <div class="track-title">${i + 1}. ${escapeHtml(item.title)}</div>
            <div class="track-artist">${escapeHtml(item.artist)} · ${formatDuration(item.duration)}</div>
          </div>
        </div>
      `
    )
    .join("");
}

export function renderCollection(state) {
  const title = state.collectionTitle || "Подборка";
  const head = `
    <div class="page-head" data-role="page-head">
      <button class="icon-btn" data-action="back" aria-label="Назад">${icon("back")}</button>
      <span>${TYPE_LABEL[state.collectionType] || "Подборка"}</span>
    </div>
  `;

  if (state.collectionStatus === "loading") {
    return `${head}<div class="empty-state">Загружаю…</div>`;
  }

  const tracks = state.collectionTracks || [];
  if (!tracks.length) {
    return `${head}<div class="empty-state">Здесь пока пусто.</div>`;
  }

  const letter = escapeHtml(title.trim()[0] || "♪").toUpperCase();
  const cover = state.collectionCover
    ? `<img class="coll-hero__cover" src="${escapeHtml(state.collectionCover)}" alt="" />`
    : `<div class="coll-hero__cover">${letter}</div>`;
  const live = state.collectionLive || [];
  const addAll = state.collectionAlbumId
    ? `<button class="btn btn--ghost" data-action="album-add-all">${icon("plus")} Добавить весь альбом</button>`
    : "";

  return `
    ${head}
    <div class="coll-hero">
      ${cover}
      <div class="coll-hero__title">${escapeHtml(title)}</div>
      <div class="coll-hero__meta">${tracks.length} треков · ${totalDuration(tracks)}</div>
      <div class="coll-hero__actions">
        <button class="btn btn--primary" data-action="collection-play">${icon("play")} Слушать</button>
        <button class="btn btn--ghost" data-action="collection-shuffle">${icon("shuffle")} Перемешать</button>
        ${addAll}
      </div>
    </div>
    <div class="card home-track-card">${
      live.length ? renderLiveRows(live) : renderTrackList(tracks, { context: "collection", state })
    }</div>
  `;
}

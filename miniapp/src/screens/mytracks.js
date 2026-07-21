import { icon } from "../components/icons.js";
import { renderCover } from "../components/cover.js";
import { escapeHtml } from "../components/trackRow.js";
import { formatDuration } from "../api.js";
import { offlineTracks } from "../offline.js";

// «Мои треки» по референсу VK Music (ТЗ §5): вкладки Все/Скачанные, поиск,
// Shuffle + Sort By, режим редактирования с удалением из библиотеки.

export const SORT_OPTIONS = [
  { id: "default", label: "По умолчанию" },
  { id: "newest", label: "Сначала новые" },
  { id: "oldest", label: "Сначала старые" },
  { id: "title", label: "По названию" },
  { id: "artist", label: "По исполнителю" },
];

export function myTracksList(state) {
  const source = state.myTracksTab === "downloaded" ? offlineTracks() : state.libraryPageItems;
  const query = state.myTracksQuery.trim().toLowerCase();
  let list = query
    ? source.filter(
        (t) =>
          (t.title || "").toLowerCase().includes(query) ||
          (t.artist || "").toLowerCase().includes(query)
      )
    : [...source];

  switch (state.myTracksSort) {
    case "newest":
      list.sort((a, b) => b.id - a.id);
      break;
    case "oldest":
      list.sort((a, b) => a.id - b.id);
      break;
    case "title":
      list.sort((a, b) => (a.title || "").localeCompare(b.title || "", "ru"));
      break;
    case "artist":
      list.sort((a, b) => (a.artist || "").localeCompare(b.artist || "", "ru"));
      break;
    default:
      break;
  }
  return list;
}

function trackRow(track, state) {
  const playing = state.currentTrack && state.currentTrack.id === track.id;
  const trailing = state.myTracksEdit
    ? `<button class="icon-btn mt-remove" data-action="mytracks-remove" data-id="${track.id}" aria-label="Удалить">${icon("trash")}</button>`
    : `
      <button class="icon-btn" data-action="download" data-id="${track.id}" aria-label="Скачать">${icon("download")}</button>
      <button class="icon-btn" data-action="open-sheet" data-id="${track.id}" aria-label="Ещё">${icon("more")}</button>
    `;
  return `
    <div class="track-row${playing ? " is-playing" : ""}" data-action="play-track" data-id="${track.id}" data-context="mytracks">
      ${renderCover(track)}
      <div class="track-info">
        <div class="track-title">${escapeHtml(track.title)}</div>
        <div class="track-artist">${escapeHtml(track.artist)} · ${formatDuration(track.duration)}</div>
      </div>
      <div class="track-actions">${trailing}</div>
    </div>
  `;
}

function renderSortSheet(state) {
  if (!state.sortSheetOpen) return "";
  const rows = SORT_OPTIONS.map(
    (o) => `
      <button class="sheet-item" data-action="mytracks-sort" data-value="${o.id}">
        <span style="flex:1;text-align:left">${o.label}</span>
        ${state.myTracksSort === o.id ? icon("check") : ""}
      </button>
    `
  ).join("");
  return `
    <div class="sheet-overlay" data-action="close-sort-sheet">
      <div class="sheet" data-action="noop">
        <div class="sheet__handle"></div>
        <div class="sheet__title">Сортировка</div>
        ${rows}
      </div>
    </div>
  `;
}

// Шит «…» в шапке — как в VK (копи/ photo_1): скачать всё / редактировать / удалить скачанные
function renderMenuSheet(state) {
  if (!state.myTracksMenuOpen) return "";
  const downloaded = offlineTracks().length;
  return `
    <div class="sheet-overlay" data-action="close-mytracks-menu">
      <div class="sheet" data-action="noop">
        <div class="sheet__handle"></div>
        <button class="sheet-item" data-action="mytracks-download-all">
          ${icon("download")}<span style="flex:1;text-align:left">Скачать всё</span>
        </button>
        <button class="sheet-item" data-action="mytracks-edit-from-menu">
          ${icon("pencil")}<span style="flex:1;text-align:left">Редактировать мои треки</span>
        </button>
        <button class="sheet-item${downloaded ? "" : " is-disabled"}" data-action="clear-offline" style="color:#e35d6a">
          ${icon("trash")}<span style="flex:1;text-align:left">Удалить скачанные треки</span>
        </button>
        <button class="sheet-item" data-action="close-mytracks-menu">
          <span style="flex:1;text-align:center;font-weight:700">Закрыть</span>
        </button>
      </div>
    </div>
  `;
}

export function renderMyTracks(state) {
  const list = myTracksList(state);
  const isDownloads = state.myTracksTab === "downloaded";
  const sortLabel = (SORT_OPTIONS.find((o) => o.id === state.myTracksSort) || SORT_OPTIONS[0]).label;

  const head = `
    <div class="page-head" data-role="page-head">
      <button class="icon-btn" data-action="back" aria-label="Назад">${icon("back")}</button>
      <span>Мои треки</span>
      <span style="display:flex;gap:6px">
        <button class="icon-btn page-head__action${state.myTracksEdit ? " is-active" : ""}" data-action="mytracks-edit" aria-label="Редактировать">${icon("pencil")}</button>
        <button class="icon-btn page-head__action" data-action="open-mytracks-menu" aria-label="Ещё">${icon("more")}</button>
      </span>
    </div>
  `;

  const tabs = `
    <div class="seg-row">
      <button class="seg${isDownloads ? "" : " is-active"}" data-action="mytracks-tab" data-tab="all">
        Все <span class="seg__count">${state.libraryTotal}</span>
      </button>
      <button class="seg${isDownloads ? " is-active" : ""}" data-action="mytracks-tab" data-tab="downloaded">
        Скачанные <span class="seg__count">${offlineTracks().length}</span>
      </button>
    </div>
  `;

  const searchBox = `
    <div class="search-input search-input--compact">
      ${icon("search")}
      <input type="text" data-role="mytracks-search" placeholder="Search" value="${escapeHtml(state.myTracksQuery)}" />
    </div>
  `;

  const toolbar = `
    <div class="mt-toolbar">
      <button class="mt-shuffle" data-action="mytracks-shuffle">${icon("shuffle")}<span>Перемешать</span></button>
      <button class="mt-sort" data-action="open-sort-sheet">${sortLabel} ${icon("chevron-down")}</button>
    </div>
  `;

  return `${head}${tabs}${searchBox}${toolbar}<div id="mytracks-body">${renderMyTracksBody(state)}</div>${renderSortSheet(state)}${renderMenuSheet(state)}`;
}

// Тело списка — отдельно: ввод в поиске перерисовывает только его (фокус не теряется)
export function renderMyTracksBody(state) {
  const list = myTracksList(state);
  const isDownloads = state.myTracksTab === "downloaded";
  if (!list.length) {
    return isDownloads
      ? '<div class="empty-state">Нет скачанных треков.<br />«Ещё» у трека → «Сохранить офлайн» (Premium).</div>'
      : state.myTracksQuery.trim()
        ? `<div class="empty-state">Ничего не найдено по «${escapeHtml(state.myTracksQuery.trim())}»</div>`
        : '<div class="empty-state">Библиотека пуста.<br />Добавляйте треки кнопкой «+» из поиска.</div>';
  }
  const more =
    !isDownloads && !state.myTracksQuery.trim() && state.libraryPageItems.length < state.libraryTotal
      ? '<button class="btn btn--ghost btn--block" style="margin-top:12px" data-action="library-more">Показать ещё</button>'
      : "";
  return `<div class="card home-track-card">${list.map((t) => trackRow(t, state)).join("")}</div>${more}`;
}

import { icon } from "../components/icons.js";
import { escapeHtml } from "../components/trackRow.js";

// Список плейлистов по референсу VK Music (ТЗ §6): строки с квадратной обложкой,
// сверху — «Создать плейлист» (инлайн-форма без всплывающих окон).

function playlistCover(title) {
  const letter = escapeHtml((title || "?").trim()[0] || "?").toUpperCase();
  return `<span class="pl-cover">${letter}</span>`;
}

export function renderPlaylists(state) {
  const head = `
    <div class="page-head" data-role="page-head">
      <button class="icon-btn" data-action="back" aria-label="Назад">${icon("back")}</button>
      <span>Плейлисты</span>
    </div>
  `;

  if (state.playlistsStatus === "loading") {
    return `${head}<div class="empty-state">Загружаю…</div>`;
  }

  const createRow = state.playlistCreating
    ? `
      <div class="pl-create-form">
        <input type="text" data-role="playlist-title" placeholder="Название плейлиста" maxlength="100" />
        <button class="btn btn--primary" data-action="playlist-create-submit">Создать</button>
        <button class="btn btn--ghost" data-action="playlist-create-cancel">Отмена</button>
      </div>
    `
    : `
      <button class="pl-row pl-row--create" data-action="playlist-create">
        <span class="pl-cover pl-cover--create">${icon("plus")}</span>
        <span class="pl-row__title" style="color:var(--text-accent)">Создать плейлист</span>
      </button>
    `;

  const playlists = state.playlists || [];
  const rows = playlists
    .map(
      (p) => `
        <button class="pl-row" data-action="open-playlist" data-id="${p.id}" data-title="${escapeHtml(p.title)}">
          ${playlistCover(p.title)}
          <span class="pl-row__text">
            <span class="pl-row__title">${escapeHtml(p.title)}</span>
            <span class="pl-row__sub">${p.track_count} треков</span>
          </span>
          ${icon("chevron")}
        </button>
      `
    )
    .join("");

  return `
    ${head}
    ${createRow}
    ${rows || '<div class="empty-state">Плейлистов пока нет — создайте первый.</div>'}
  `;
}

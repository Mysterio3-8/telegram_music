import { icon } from "../components/icons.js";
import { escapeHtml } from "../components/trackRow.js";
import { getFavoriteArtists } from "../prefs.js";

// Исполнители (ТЗ §13-14): дедуплицированный список с сервера, тап открывает
// треки исполнителя. Сердечко — «любимый исполнитель» для рекомендаций.

export function renderArtists(state) {
  const head = `
    <div class="page-head" data-role="page-head">
      <button class="icon-btn" data-action="back" aria-label="Назад">${icon("back")}</button>
      <span>Исполнители</span>
    </div>
  `;

  if (state.artistsStatus === "loading") {
    return `${head}<div class="empty-state">Загружаю…</div>`;
  }

  const artists = state.artists || [];
  if (!artists.length) {
    return `${head}<div class="empty-state">В базе пока нет исполнителей</div>`;
  }

  const favorites = new Set(getFavoriteArtists().map((a) => a.toLowerCase()));

  const list = artists
    .map((a) => {
      const active = favorites.has(a.name.toLowerCase());
      return `
        <div class="artist-row${active ? " is-fav" : ""}" data-action="open-artist" data-artist="${escapeHtml(a.name)}">
          <span class="artist-row__avatar">${escapeHtml((a.name[0] || "?").toUpperCase())}</span>
          <span class="artist-row__info">
            <span class="artist-row__name">${escapeHtml(a.name)}</span>
            <span class="artist-row__count">${a.track_count} треков</span>
          </span>
          <button class="artist-row__heart icon-btn" data-action="toggle-artist" data-artist="${escapeHtml(a.name)}" aria-label="В любимые">${icon("heart")}</button>
        </div>
      `;
    })
    .join("");

  return `
    ${head}
    <p class="page-hint">Отмечайте сердечком любимых — это улучшит рекомендации.</p>
    <div class="artist-list">${list}</div>
  `;
}

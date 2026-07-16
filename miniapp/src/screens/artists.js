import { icon } from "../components/icons.js";
import { escapeHtml } from "../components/trackRow.js";
import { getFavoriteArtists } from "../prefs.js";

// Исполнители из базы. В избранное — локально (предпочтения пользователя).
function distinctArtists(state) {
  const map = new Map(); // ключ в нижнем регистре → { name: исходный регистр, count }
  for (const track of state.catalog) {
    const artist = (track.artist || "").trim();
    if (!artist) continue;
    const key = artist.toLowerCase();
    const entry = map.get(key);
    if (entry) entry.count += 1;
    else map.set(key, { name: artist, count: 1 });
  }
  return [...map.values()].sort((a, b) => b.count - a.count);
}

export function renderArtists(state) {
  const artists = distinctArtists(state);
  const favorites = new Set(getFavoriteArtists().map((a) => a.toLowerCase()));

  const list = artists
    .map((a) => {
      const active = favorites.has(a.name.toLowerCase());
      return `
        <button class="artist-row${active ? " is-fav" : ""}" data-action="toggle-artist" data-artist="${escapeHtml(a.name)}">
          <span class="artist-row__avatar">${escapeHtml(a.name[0] || "?").toUpperCase()}</span>
          <span class="artist-row__info">
            <span class="artist-row__name">${escapeHtml(a.name)}</span>
            <span class="artist-row__count">${a.count} треков</span>
          </span>
          <span class="artist-row__heart">${icon("heart")}</span>
        </button>
      `;
    })
    .join("");

  return `
    <div class="page-head" data-role="page-head">
      <button class="icon-btn" data-action="nav" data-screen="settings" aria-label="Назад">${icon("back")}</button>
      <span>Любимые исполнители</span>
    </div>
    <p class="page-hint">Отметьте исполнителей, чтобы улучшить рекомендации.</p>
    ${
      artists.length
        ? `<div class="artist-list">${list}</div>`
        : '<div class="empty-state">В базе пока нет исполнителей</div>'
    }
  `;
}

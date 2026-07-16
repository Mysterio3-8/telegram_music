import { icon } from "../components/icons.js";
import { renderTrackList, escapeHtml } from "../components/trackRow.js";
import { getRecentSearches } from "../prefs.js";

const POPULAR_LIMIT = 8;

// «Популярные запросы» — исполнители из базы (данные реальные, не выдуманный список).
function popularQueries(state) {
  const seen = new Set();
  const out = [];
  for (const track of state.catalog) {
    const artist = (track.artist || "").trim();
    const key = artist.toLowerCase();
    if (artist && !seen.has(key)) {
      seen.add(key);
      out.push(artist);
    }
    if (out.length >= POPULAR_LIMIT) break;
  }
  return out;
}

function chip(query, action) {
  return `
    <button class="search-chip" data-action="${action}" data-q="${escapeHtml(query)}">
      ${icon("search")}<span>${escapeHtml(query)}</span>
    </button>
  `;
}

function renderSuggestions(state) {
  const popular = popularQueries(state);
  const recent = getRecentSearches();

  const popularBlock = popular.length
    ? `
      <div class="section-head"><span class="section-title">Популярные запросы</span></div>
      <div class="chip-cloud">${popular.map((q) => chip(q, "search-chip")).join("")}</div>
    `
    : "";

  const recentBlock = recent.length
    ? `
      <div class="section-head section-head--between">
        <span class="section-title">Недавние запросы</span>
        <button class="link-more" data-action="clear-recent-searches">Очистить</button>
      </div>
      <div class="chip-cloud">${recent.map((q) => chip(q, "search-chip")).join("")}</div>
    `
    : "";

  if (!popularBlock && !recentBlock) {
    return '<div class="empty-state">В базе пока нет треков</div>';
  }
  return `${popularBlock}${recentBlock}`;
}

// Результаты живут в отдельном контейнере: ввод перерисовывает только его,
// а не всё приложение (иначе инпут теряет фокус).
export function renderSearchResults(state) {
  const query = state.searchQuery.trim();
  if (!query) {
    return renderSuggestions(state);
  }
  if (state.searchStatus === "loading") {
    return '<div class="empty-state">Ищу…</div>';
  }
  if (!state.searchResults.length) {
    return `<div class="empty-state">Ничего не найдено по «${escapeHtml(query)}»</div>`;
  }
  return `
    <div class="section-head"><span class="section-title">Найдено: ${state.searchTotal}</span></div>
    <div class="card">${renderTrackList(state.searchResults, { context: "search", state })}</div>
  `;
}

export function renderSearch(state) {
  return `
    <div class="search-input">
      ${icon("search")}
      <input type="text" data-role="search-input" placeholder="Трек или исполнитель" value="${escapeHtml(state.searchQuery)}" />
    </div>
    <div id="search-results">${renderSearchResults(state)}</div>
  `;
}

import { icon } from "../components/icons.js";
import { renderTrackList, escapeHtml } from "../components/trackRow.js";

const TOP_LIMIT = 10;

// Результаты живут в отдельном контейнере: ввод в поиске перерисовывает только его,
// а не всё приложение (иначе инпут теряет фокус и всё дёргается).
export function renderSearchResults(state) {
  const query = state.searchQuery.trim();
  if (!query) {
    const top = state.catalog.slice(0, TOP_LIMIT);
    if (!top.length) return '<div class="empty-state">В базе пока нет треков</div>';
    return `
      <div class="section-head">
        <span class="section-title">Популярное сейчас</span>
      </div>
      <div class="card">${renderTrackList(top, { context: "catalog", state })}</div>
    `;
  }
  if (state.searchStatus === "loading") {
    return '<div class="empty-state">Ищу…</div>';
  }
  if (!state.searchResults.length) {
    return `<div class="empty-state">Ничего не найдено по «${escapeHtml(query)}»</div>`;
  }
  return `
    <div class="section-head">
      <span class="section-title">Найдено: ${state.searchTotal}</span>
    </div>
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

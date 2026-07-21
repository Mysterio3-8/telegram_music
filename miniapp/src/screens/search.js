import { icon } from "../components/icons.js";
import { renderTrackList, escapeHtml } from "../components/trackRow.js";
import { getRecentSearches, getRecentTracks } from "../prefs.js";

// Поиск (ТЗ §11 + скрины VK в копи/): сверху «История прослушивания» (недавние
// треки), затем недавние запросы пользователя и реальные популярные запросы
// (статистика сервера, без выдуманных списков).

function chip(query) {
  return `
    <button class="search-chip" data-action="search-chip" data-q="${escapeHtml(query)}">
      ${icon("search")}<span>${escapeHtml(query)}</span>
    </button>
  `;
}

function renderSuggestions(state) {
  const recent = getRecentSearches();
  const popular = (state.popularQueries || []).filter(
    (q) => !recent.some((r) => r.toLowerCase() === q.toLowerCase())
  );

  const historyTracks = getRecentTracks().slice(0, 5);
  const historyBlock = historyTracks.length
    ? `
      <div class="section-head section-head--between">
        <span class="section-title">История прослушивания</span>
        <button class="link-more" data-action="open-recent">Все</button>
      </div>
      <div class="card">${renderTrackList(historyTracks, { context: "recent", state })}</div>
    `
    : "";

  const recentBlock = recent.length
    ? `
      <div class="section-head section-head--between">
        <span class="section-title">Недавние запросы</span>
        <button class="link-more" data-action="clear-recent-searches">Очистить</button>
      </div>
      <div class="chip-cloud">${recent.map(chip).join("")}</div>
    `
    : "";

  const popularBlock = popular.length
    ? `
      <div class="section-head"><span class="section-title">Популярные запросы</span></div>
      <div class="chip-cloud">${popular.map(chip).join("")}</div>
    `
    : "";

  if (!historyBlock && !recentBlock && !popularBlock) {
    return '<div class="empty-state">Введите название трека или исполнителя</div>';
  }
  return `${historyBlock}${recentBlock}${popularBlock}`;
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
  const isInstrumentals = state.searchMode === "instrumentals";
  return `
    <div class="pill-row search-mode">
      <button class="pill${isInstrumentals ? "" : " is-active"}" data-action="search-mode" data-mode="tracks">Треки</button>
      <button class="pill${isInstrumentals ? " is-active" : ""}" data-action="search-mode" data-mode="instrumentals">🎼 Минусы</button>
    </div>
    <div class="search-input">
      ${icon("search")}
      <input type="text" data-role="search-input" placeholder="Search" value="${escapeHtml(state.searchQuery)}" />
    </div>
    <div id="search-results">${renderSearchResults(state)}</div>
  `;
}

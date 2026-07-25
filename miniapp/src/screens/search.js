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

  // Жанры каталога (SPEC-КАТАЛОГ §1): топ-уровень дерева как чипы, тап → экран жанра
  const genres = state.genres || [];
  const genresBlock = genres.length
    ? `
      <div class="section-head"><span class="section-title">Жанры</span></div>
      <div class="chip-cloud">${genres
        .map(
          (g) => `
            <button class="search-chip" data-action="open-genre" data-slug="${escapeHtml(g.slug)}" data-name="${escapeHtml(g.name)}">
              <span>${escapeHtml(g.name)}</span>
            </button>
          `
        )
        .join("")}</div>
    `
    : "";

  if (!historyBlock && !recentBlock && !popularBlock && !genresBlock) {
    return '<div class="empty-state">Введите название трека или исполнителя</div>';
  }
  return `${historyBlock}${recentBlock}${popularBlock}${genresBlock}`;
}

// Секционная выдача (референс): Артисты / Альбомы / Плейлисты / Треки.
function renderSections(sections, state) {
  const blocks = [];

  if (sections.artists && sections.artists.length) {
    const cards = sections.artists
      .map((a) => {
        const avatar = a.photo_url
          ? `<img class="similar-artist__avatar" src="${escapeHtml(a.photo_url)}" alt="" loading="lazy" />`
          : `<span class="similar-artist__avatar similar-artist__avatar--letter">${escapeHtml((a.name[0] || "♪").toUpperCase())}</span>`;
        return `
          <button class="similar-artist" data-action="open-artist" data-artist="${escapeHtml(a.name)}">
            ${avatar}<span class="similar-artist__name">${escapeHtml(a.name)}</span>
          </button>
        `;
      })
      .join("");
    blocks.push(`
      <div class="section-head"><span class="section-title">Артисты</span></div>
      <div class="similar-artists">${cards}</div>
    `);
  }

  if (sections.albums && sections.albums.length) {
    const cards = sections.albums
      .map(
        (a) => `
          <button class="artist-album" data-action="open-album" data-name="${escapeHtml(a.name)}">
            ${
              a.cover_url
                ? `<img class="artist-album__cover" src="${escapeHtml(a.cover_url)}" alt="" loading="lazy" />`
                : `<span class="artist-album__cover artist-album__cover--letter">${escapeHtml((a.name[0] || "♪").toUpperCase())}</span>`
            }
            <span class="artist-album__name">${escapeHtml(a.name)}</span>
            <span class="artist-album__count">${a.track_count} треков</span>
          </button>
        `
      )
      .join("");
    blocks.push(`
      <div class="section-head"><span class="section-title">Альбомы</span></div>
      <div class="artist-albums">${cards}</div>
    `);
  }

  if (sections.playlists && sections.playlists.length) {
    const rows = sections.playlists
      .map(
        (p) => `
          <button class="lib-row" data-action="open-playlist" data-id="${p.id}" data-title="${escapeHtml(p.title)}">
            ${icon("playlist")}
            <span class="lib-row__text"><span class="lib-row__title">${escapeHtml(p.title)}</span>
            <span class="lib-row__sub">${p.track_count} треков</span></span>
          </button>
        `
      )
      .join("");
    blocks.push(`
      <div class="section-head"><span class="section-title">Плейлисты</span></div>
      <div class="card">${rows}</div>
    `);
  }

  if (sections.tracks && sections.tracks.length) {
    blocks.push(`
      <div class="section-head"><span class="section-title">Треки</span></div>
      <div class="card">${renderTrackList(sections.tracks, { context: "search", state })}</div>
    `);
  }

  return blocks.join("");
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

  // Минусы — плоский список; треки — секционная выдача
  if (state.searchMode === "instrumentals") {
    if (!state.searchResults.length) {
      return `<div class="empty-state">Ничего не найдено по «${escapeHtml(query)}»</div>`;
    }
    return `
      <div class="section-head"><span class="section-title">Найдено: ${state.searchTotal}</span></div>
      <div class="card">${renderTrackList(state.searchResults, { context: "search", state })}</div>
    `;
  }

  const sections = state.searchSections;
  const hasAny =
    sections &&
    (sections.artists.length || sections.albums.length || sections.playlists.length || sections.tracks.length);
  if (!hasAny) {
    return `<div class="empty-state">Ничего не найдено по «${escapeHtml(query)}»</div>`;
  }
  return renderSections(sections, state);
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

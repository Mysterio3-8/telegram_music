import { icon } from "../components/icons.js";
import { renderTrackList, escapeHtml } from "../components/trackRow.js";

// Карточка артиста (SPEC-КАТАЛОГ §2): баннер, аватар, жанры-чипы, описание,
// «Слушать всё», топ треков, альбомы. Живёт даже у артиста без фото/жанров.

function heroStyle(card) {
  return card.banner_url
    ? ` style="background-image:linear-gradient(to bottom, rgba(15,15,16,.35), rgba(15,15,16,.95)), url('${escapeHtml(card.banner_url)}')"`
    : "";
}

function avatar(card) {
  if (card.photo_url) {
    return `<img class="artist-hero__avatar" src="${escapeHtml(card.photo_url)}" alt="" loading="lazy" />`;
  }
  const letter = escapeHtml((card.name.trim()[0] || "♪").toUpperCase());
  return `<div class="artist-hero__avatar artist-hero__avatar--letter">${letter}</div>`;
}

export function renderArtistCard(state) {
  const head = `
    <div class="page-head" data-role="page-head">
      <button class="icon-btn" data-action="back" aria-label="Назад">${icon("back")}</button>
      <span>Исполнитель</span>
    </div>
  `;

  if (state.artistCardStatus === "loading" || !state.artistCard) {
    return `${head}<div class="empty-state">Загружаю…</div>`;
  }
  if (state.artistCardStatus === "error") {
    return `${head}<div class="empty-state">Не удалось загрузить карточку</div>`;
  }

  const card = state.artistCard;
  const name = escapeHtml(card.name);

  const genresBlock = card.genres.length
    ? `<div class="chip-cloud artist-hero__genres">${card.genres
        .map((g) => `<span class="search-chip">${escapeHtml(g)}</span>`)
        .join("")}</div>`
    : "";

  const description = card.description
    ? `<p class="artist-card__desc">${escapeHtml(card.description)}</p>`
    : "";

  const topBlock = card.top_tracks.length
    ? `
      <div class="section-head"><span class="section-title">Топ треков</span></div>
      <div class="card">${renderTrackList(card.top_tracks, { context: "collection", state })}</div>
    `
    : '<div class="empty-state">Треки этого артиста ещё загружаются в базу</div>';

  const albumsBlock = card.albums.length
    ? `
      <div class="section-head"><span class="section-title">Альбомы</span></div>
      <div class="artist-albums">${card.albums
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
        .join("")}</div>
    `
    : "";

  const actions = card.track_count
    ? `
      <div class="coll-hero__actions">
        <button class="btn btn--primary" data-action="artist-play-all" data-artist="${name}">${icon("play")} Слушать всё</button>
        <button class="btn btn--ghost" data-action="open-artist-tracks" data-artist="${name}">Все треки (${card.track_count})</button>
      </div>
    `
    : "";

  return `
    ${head}
    <div class="artist-hero"${heroStyle(card)}>
      ${avatar(card)}
      <div class="artist-hero__name">${name}</div>
      ${genresBlock}
      ${actions}
    </div>
    ${description}
    ${topBlock}
    ${albumsBlock}
  `;
}

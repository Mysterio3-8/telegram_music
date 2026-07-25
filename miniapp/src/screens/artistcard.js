import { icon } from "../components/icons.js";
import { renderTrackList, escapeHtml } from "../components/trackRow.js";
import { renderCover } from "../components/cover.js";

// Карточка артиста (SPEC-КАТАЛОГ §2 + референсы Яндекс/VK): баннер, аватар,
// жанры, подписка, последний релиз, топ треков, синглы, альбомы, похожие артисты.

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

function latestReleaseBlock(track) {
  if (!track) return "";
  return `
    <div class="latest-release">
      <div class="latest-release__label">Последний релиз</div>
      <div class="latest-release__body" data-action="play-track" data-id="${track.id}">
        ${renderCover(track)}
        <div class="latest-release__info">
          <div class="track-title">${escapeHtml(track.title)}</div>
          <div class="track-artist">Сингл</div>
        </div>
        <button class="icon-btn latest-release__play" data-action="play-track" data-id="${track.id}">${icon("play")}</button>
      </div>
    </div>
  `;
}

function similarBlock(similar) {
  if (!similar || !similar.length) return "";
  const cards = similar
    .map((s) => {
      const avatarHtml = s.photo_url
        ? `<img class="similar-artist__avatar" src="${escapeHtml(s.photo_url)}" alt="" loading="lazy" />`
        : `<span class="similar-artist__avatar similar-artist__avatar--letter">${escapeHtml((s.name[0] || "♪").toUpperCase())}</span>`;
      return `
        <button class="similar-artist" data-action="open-artist" data-artist="${escapeHtml(s.name)}">
          ${avatarHtml}
          <span class="similar-artist__name">${escapeHtml(s.name)}</span>
        </button>
      `;
    })
    .join("");
  return `
    <div class="section-head"><span class="section-title">Похожие артисты</span></div>
    <div class="similar-artists">${cards}</div>
  `;
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

  // Подписка — только если у артиста есть сущность в базе (artist_id)
  const followBtn = card.artist_id
    ? `<button class="btn ${card.following ? "btn--ghost" : "btn--outline"} artist-hero__follow" data-action="toggle-follow" data-id="${card.artist_id}">
         ${card.following ? icon("check") + " Вы подписаны" : icon("plus") + " Подписаться"}
       </button>`
    : "";

  const actions = card.track_count
    ? `
      <div class="coll-hero__actions">
        <button class="btn btn--primary" data-action="artist-play-all" data-artist="${name}">${icon("play")} Слушать всё</button>
        <button class="btn btn--ghost" data-action="artist-play-similar" data-artist="${name}">${icon("radio")} Слушать похожее</button>
      </div>
    `
    : "";

  const topBlock = card.top_tracks.length
    ? `
      <div class="section-head section-head--between">
        <span class="section-title">Топ треков</span>
        <button class="link-more" data-action="open-artist-tracks" data-artist="${name}">Все ${card.track_count}</button>
      </div>
      <div class="card">${renderTrackList(card.top_tracks.slice(0, 5), { context: "collection", state })}</div>
    `
    : '<div class="empty-state">Треки этого артиста ещё загружаются в базу</div>';

  const singlesBlock = card.singles && card.singles.length
    ? `
      <div class="section-head"><span class="section-title">Синглы</span></div>
      <div class="card">${renderTrackList(card.singles, { context: "collection", state })}</div>
    `
    : "";

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

  return `
    ${head}
    <div class="artist-hero"${heroStyle(card)}>
      ${avatar(card)}
      <div class="artist-hero__name">${name}</div>
      ${genresBlock}
      ${followBtn}
      ${actions}
    </div>
    ${latestReleaseBlock(card.latest_release)}
    ${description}
    ${topBlock}
    ${singlesBlock}
    ${albumsBlock}
    ${similarBlock(card.similar)}
  `;
}

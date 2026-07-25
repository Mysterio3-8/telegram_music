import { icon } from "../components/icons.js";
import { escapeHtml } from "../components/trackRow.js";

// «Мои артисты» — подписки пользователя (референс: раздел библиотеки).
// Тап по строке открывает карточку артиста.

export function renderMyArtists(state) {
  const head = `
    <div class="page-head" data-role="page-head">
      <button class="icon-btn" data-action="back" aria-label="Назад">${icon("back")}</button>
      <span>Мои артисты</span>
    </div>
  `;

  if (state.myArtistsStatus === "loading") {
    return `${head}<div class="empty-state">Загружаю…</div>`;
  }

  const artists = state.myArtists || [];
  if (!artists.length) {
    return `${head}<div class="empty-state">Вы ещё не подписаны ни на одного артиста. Откройте карточку артиста и нажмите «Подписаться».</div>`;
  }

  const list = artists
    .map((a) => {
      const avatarHtml = a.photo_url
        ? `<img class="artist-row__avatar-img" src="${escapeHtml(a.photo_url)}" alt="" loading="lazy" />`
        : `<span class="artist-row__avatar">${escapeHtml((a.name[0] || "?").toUpperCase())}</span>`;
      return `
        <div class="artist-row" data-action="open-artist" data-artist="${escapeHtml(a.name)}">
          ${avatarHtml}
          <span class="artist-row__info">
            <span class="artist-row__name">${escapeHtml(a.name)}</span>
            <span class="artist-row__count">${a.track_count} треков</span>
          </span>
          <button class="artist-row__heart icon-btn" data-action="unfollow-artist" data-id="${a.id}" aria-label="Отписаться">${icon("check")}</button>
        </div>
      `;
    })
    .join("");

  return `${head}<div class="artist-list">${list}</div>`;
}

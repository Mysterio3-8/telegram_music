import { icon } from "../components/icons.js";
import { renderTrackRow, renderTrackList } from "../components/trackRow.js";

const COLUMN_SIZE = 3;

function chunk(list, size) {
  const out = [];
  for (let i = 0; i < list.length; i += size) out.push(list.slice(i, i + size));
  return out;
}

// «Мои треки»: блоки по 3 трека, свайп вправо открывает следующий блок.
function renderMyTracks(state) {
  const { libraryPageItems, libraryTotal } = state;
  if (!libraryTotal) {
    return `
      <div class="empty-state">
        Библиотека пуста.<br />Добавляйте треки кнопкой «+» из поиска.
      </div>
    `;
  }

  const columns = chunk(libraryPageItems, COLUMN_SIZE)
    .map(
      (col) => `
        <div class="lib-col">
          ${col
            .map((t) =>
              renderTrackRow(t, {
                context: "library",
                inLibrary: state.libraryIds.has(t.id),
                playing: state.currentTrack && state.currentTrack.id === t.id,
              })
            )
            .join("")}
        </div>
      `
    )
    .join("");

  const more =
    libraryPageItems.length < libraryTotal
      ? '<button class="btn btn--ghost btn--block" style="margin-top:12px" data-action="library-more">Показать ещё</button>'
      : "";

  return `<div class="lib-cols h-scroll">${columns}</div>${more}`;
}

function renderMixButtons() {
  const buttons = [
    { action: "play-mix", mix: "library-shuffle", ic: "shuffle", label: "Мой микс" },
    { action: "play-mix", mix: "library", ic: "heart", label: "Любимые" },
    { action: "play-recommended", ic: "sparkles", label: "Рекомендации" },
  ];
  return `
    <div class="lib-mix-row">
      ${buttons
        .map(
          (b) => `
        <button class="lib-mix-btn" data-action="${b.action}"${b.mix ? ` data-mix="${b.mix}"` : ""}>
          <span class="lib-mix-btn__icon">${icon(b.ic)}</span>
          <span>${b.label}</span>
        </button>
      `
        )
        .join("")}
    </div>
  `;
}

function renderMore(state) {
  const premiumCard =
    state.premium && state.premium.active
      ? `
        <div class="premium-card">
          <div class="premium-card__icon">${icon("crown")}</div>
          <div>
            <div class="premium-card__title">TG Music Premium активен</div>
            <div class="premium-card__subtitle">Без рекламы и лимитов</div>
          </div>
        </div>
      `
      : `
        <div class="premium-card" data-action="pay-premium">
          <div class="premium-card__icon">${icon("crown")}</div>
          <div>
            <div class="premium-card__title">TG Music Premium</div>
            <div class="premium-card__subtitle">30 дней — ${state.premium ? state.premium.price_rub : 21} ₽</div>
          </div>
        </div>
      `;

  const tiles = [
    { ic: "history", label: "Недавно прослушанные", action: "open-recent" },
    { ic: "playlist", label: "Плейлисты", action: "open-playlists" },
    { ic: "album", label: "Альбомы", action: "open-albums" },
    { ic: "mic", label: "Исполнители", action: "open-artists" },
    { ic: "star", label: "Кураторы", action: "open-curators" },
    { ic: "download", label: "Загрузки", action: "open-downloads" },
    { ic: "globe", label: "Онлайн-треки", action: "nav", screen: "search" },
  ];

  const grid = tiles
    .map(
      (t) => `
        <button class="more-tile" data-action="${t.action}"${t.screen ? ` data-screen="${t.screen}"` : ""}>
          <span class="more-tile__icon">${icon(t.ic)}</span>
          <span class="more-tile__label">${t.label}</span>
        </button>
      `
    )
    .join("");

  return `
    <div class="section-head"><span class="section-title">Ещё</span></div>
    ${premiumCard}
    <div class="more-grid">${grid}</div>
  `;
}

export function renderLibrary(state) {
  return `
    <div class="lib-row"><span class="section-title">Мои треки · ${state.libraryTotal}</span></div>
    ${renderMyTracks(state)}
    ${renderMixButtons()}
    ${renderMore(state)}
  `;
}

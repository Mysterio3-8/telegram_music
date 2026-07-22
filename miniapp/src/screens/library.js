import { icon } from "../components/icons.js";

// Библиотека: разделы-строки в стиле VK. «Онлайн-треки» удалены (ТЗ §15),
// «Кураторы» заменены на «Исполнители» — куратор и есть исполнитель (ТЗ §14).

function row(label, ic, action, sub = "") {
  return `
    <button class="pl-row" data-action="${action}">
      <span class="pl-cover pl-cover--icon">${icon(ic)}</span>
      <span class="pl-row__text">
        <span class="pl-row__title">${label}</span>
        ${sub ? `<span class="pl-row__sub">${sub}</span>` : ""}
      </span>
      ${icon("chevron")}
    </button>
  `;
}

function renderPremiumCard(state) {
  if (state.premium && state.premium.active) {
    return `
      <div class="premium-card">
        <div class="premium-card__icon">${icon("crown")}</div>
        <div>
          <div class="premium-card__title">TG Music Premium активен</div>
          <div class="premium-card__subtitle">Без рекламы и лимитов</div>
        </div>
      </div>
    `;
  }
  return `
    <div class="premium-card" data-action="open-premium">
      <div class="premium-card__icon">${icon("crown")}</div>
      <div>
        <div class="premium-card__title">TG Music Premium</div>
        <div class="premium-card__subtitle">от ${state.premium ? state.premium.price_rub : 21} ₽ в месяц</div>
      </div>
    </div>
  `;
}

export function renderLibrary(state) {
  return `
    <div class="lib-mix-row">
      <button class="lib-mix-btn" data-action="play-mix" data-mix="library">
        <span class="lib-mix-btn__icon">${icon("shuffle")}</span>
        <span>Мой микс</span>
      </button>
      <button class="lib-mix-btn" data-action="play-recommended">
        <span class="lib-mix-btn__icon">${icon("sparkles")}</span>
        <span>TG MIX</span>
      </button>
    </div>

    ${row("Мои треки", "library", "open-mytracks", `${state.libraryTotal} треков`)}
    ${row("Недавно прослушанные", "history", "open-recent")}
    ${row("Плейлисты", "playlist", "open-playlists")}
    ${row("Альбомы", "album", "open-albums")}
    ${row("Исполнители", "mic", "open-artists")}

    <div class="lib-add-row">
      ${row("Загрузить трек", "import", "open-upload", "Свой файл — в библиотеку")}
      ${row("Перенести из сервисов", "transfer", "open-transfer", "Spotify · Яндекс · ВК")}
    </div>

    <div style="margin-top:16px">${renderPremiumCard(state)}</div>
  `;
}

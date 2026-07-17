import { icon } from "../components/icons.js";
import { getRecentTracks } from "../prefs.js";

// Главная по референсам VK Music (disigner/): большой hero-микс со свайпом,
// карточка подписки, плитки быстрого доступа. Списков треков на главной НЕТ
// (решение владельца — навсегда).

function heroSlides(state) {
  return [
    {
      mix: "catalog",
      title: "Слушать TG Mix",
      subtitle: "Вся музыка в случайном порядке",
      button: "",
    },
    {
      mix: "library",
      title: "Мои треки",
      subtitle: state.libraryTotal
        ? "Любимое из вашей библиотеки"
        : "Добавьте треки в библиотеку",
      button: "",
    },
    {
      mix: "recommended",
      title: "Рекомендации",
      subtitle: "Музыкальные рекомендации для вас",
      button: `<button class="hero-slide__setup" data-action="open-recommendations">${icon("tune")} Настроить</button>`,
    },
  ];
}

function renderHero(state) {
  const slides = heroSlides(state)
    .map(
      (slide) => `
        <div class="hero-slide" data-action="${slide.mix === "recommended" ? "play-recommended" : "play-mix"}" data-mix="${slide.mix}">
          <div class="hero-slide__play">${icon("play")}</div>
          <div class="hero-slide__title">${slide.title}</div>
          <div class="hero-slide__subtitle">${slide.subtitle}</div>
          ${slide.button}
        </div>
      `
    )
    .join("");

  return `
    <div class="hero">
      <div class="hero__track h-scroll" data-role="hero-scroll">${slides}</div>
      <div class="hero__hint">${icon("chevron-left")}<span>Свайпните — другой микс</span>${icon("chevron")}</div>
    </div>
  `;
}

function renderSubscription(state) {
  if (!state.premium || state.premium.active || state.subDismissed) return "";
  return `
    <div class="sub-card" data-action="pay-premium">
      <button class="sub-card__close" data-action="dismiss-sub" aria-label="Скрыть">${icon("close")}</button>
      <div class="sub-card__title">Целый месяц — ${state.premium.price_rub} ₽</div>
      <div class="sub-card__subtitle">Premium: без рекламы и офлайн</div>
      <span class="sub-card__cta">Подключить</span>
    </div>
  `;
}

function renderTiles(state) {
  const recentCount = getRecentTracks().length;
  const tiles = [
    {
      action: "nav",
      screen: "library",
      ic: "library",
      title: "Мои треки",
      sub: String(state.libraryTotal),
    },
    {
      action: "open-recent",
      ic: "history",
      title: "Недавно прослушанные",
      sub: recentCount ? String(recentCount) : "",
    },
    { action: "open-playlists", ic: "playlist", title: "Плейлисты", sub: "" },
    { action: "open-downloads", ic: "download", title: "Загрузки", sub: "" },
  ];

  const items = tiles
    .map(
      (t) => `
        <button class="vk-tile" data-action="${t.action}"${t.screen ? ` data-screen="${t.screen}"` : ""}>
          <span class="vk-tile__text">
            <span class="vk-tile__title">${t.title}</span>
            ${t.sub ? `<span class="vk-tile__sub">${t.sub}</span>` : ""}
          </span>
          <span class="vk-tile__icon">${icon(t.ic)}</span>
        </button>
      `
    )
    .join("");

  return `<div class="vk-grid">${items}</div>`;
}

export function renderHome(state) {
  return `
    ${renderHero(state)}
    ${renderSubscription(state)}
    ${renderTiles(state)}
  `;
}

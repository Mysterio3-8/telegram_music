import { icon } from "../components/icons.js";
import { renderTrackList } from "../components/trackRow.js";
import { getRecentTracks } from "../prefs.js";

const HOME_LIST_LIMIT = 6;
const REC_STRIP_LIMIT = 5;

function greeting(user) {
  const hour = new Date().getHours();
  const timeWord = hour < 5 ? "Доброй ночи" : hour < 12 ? "Доброе утро" : hour < 18 ? "Добрый день" : "Добрый вечер";
  const name = user && user.first_name ? `, ${user.first_name}` : "";
  return `${timeWord}${name}`;
}

// Карусель «миксов» — свайп по горизонтали (scroll-snap), каждый вариант на всю
// ширину. Реализует паттерн «Play my tracks / Swipe to play VK Mix» из референса.
function heroSlides(state) {
  return [
    {
      mix: "catalog",
      title: "Слушать TG Mix",
      subtitle: `${state.catalogTotal} треков в случайном порядке`,
    },
    {
      mix: "library",
      title: "Любимые треки",
      subtitle: state.libraryTotal ? `${state.libraryTotal} в вашей библиотеке` : "Добавьте треки в библиотеку",
    },
    {
      mix: "discover",
      title: "Открытия",
      subtitle: "Случайная подборка из базы",
    },
  ];
}

function renderHero(state) {
  const slides = heroSlides(state)
    .map(
      (slide) => `
        <div class="hero-slide" data-action="play-mix" data-mix="${slide.mix}">
          <div class="hero-slide__play">${icon("play")}</div>
          <div class="hero-slide__title">${slide.title}</div>
          <div class="hero-slide__subtitle">${slide.subtitle}</div>
        </div>
      `
    )
    .join("");

  return `
    <div class="hero">
      <div class="hero__track h-scroll" data-role="hero-scroll">${slides}</div>
      <div class="hero__dots">
        <span class="hero__dot is-active"></span>
        <span class="hero__dot"></span>
        <span class="hero__dot"></span>
      </div>
    </div>
  `;
}

function renderRecommendations(state) {
  const strip = state.catalog.slice(HOME_LIST_LIMIT, HOME_LIST_LIMIT + REC_STRIP_LIMIT);
  return `
    <div class="section-head section-head--stack">
      <div>
        <span class="section-title">Рекомендации</span>
        <span class="section-sub">Музыкальные рекомендации для вас</span>
      </div>
      <button class="chip-btn" data-action="open-recommendations">${icon("tune")}Настроить</button>
    </div>
    <div class="card home-track-card">
      ${
        strip.length
          ? renderTrackList(strip, { context: "catalog", state })
          : '<div class="empty-state empty-state--sm">Рекомендации появятся, когда в базе станет больше треков</div>'
      }
    </div>
  `;
}

function renderSubscription(state) {
  if (!state.premium || state.premium.active || state.subDismissed) return "";
  return `
    <div class="sub-card" data-action="pay-premium">
      <button class="sub-card__close" data-action="dismiss-sub" aria-label="Скрыть">${icon("close")}</button>
      <div class="sub-card__title">Целый месяц — ${state.premium.price_rub} ₽</div>
      <div class="sub-card__subtitle">Без рекламы, офлайн-доступ и рекомендации</div>
      <span class="sub-card__cta">Подключить</span>
    </div>
  `;
}

function renderQuickAccess(state) {
  const recentCount = getRecentTracks().length;
  const tiles = [
    { action: "nav", screen: "library", ic: "library", title: "Мои треки", sub: `${state.libraryTotal} всего` },
    {
      action: "open-recent",
      ic: "history",
      title: "Недавно прослушанные",
      sub: recentCount ? `${recentCount} треков` : "Пока пусто",
    },
    { action: "open-playlists", ic: "playlist", title: "Плейлисты", sub: "Ваши подборки" },
  ];

  const items = tiles
    .map(
      (t) => `
        <button class="quick-tile" data-action="${t.action}"${t.screen ? ` data-screen="${t.screen}"` : ""}>
          <span class="quick-tile__icon">${icon(t.ic)}</span>
          <span class="quick-tile__text">
            <span class="quick-tile__title">${t.title}</span>
            <span class="quick-tile__sub">${t.sub}</span>
          </span>
        </button>
      `
    )
    .join("");

  return `<div class="quick-access">${items}</div>`;
}

export function renderHome(state) {
  const fresh = state.catalog.slice(0, HOME_LIST_LIMIT);

  return `
    <p class="home-greeting">${greeting(state.user)}</p>

    ${renderHero(state)}
    ${renderSubscription(state)}
    ${renderQuickAccess(state)}
    ${renderRecommendations(state)}

    <div class="section-head">
      <span class="section-title">Новое в базе</span>
      <button class="link-more" data-action="nav" data-screen="search">Все ${icon("chevron")}</button>
    </div>
    <div class="card home-track-card">
      ${
        fresh.length
          ? renderTrackList(fresh, { context: "catalog", state })
          : '<div class="empty-state">Треков пока нет</div>'
      }
    </div>
  `;
}

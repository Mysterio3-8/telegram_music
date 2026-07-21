import { icon } from "../components/icons.js";
import { getRecentTracks } from "../prefs.js";

// Главная — копия главного экрана VK Музыки (скрины владельца в копи/):
// полноэкранный hero «Слушать TG Микс» с сине-розовым волновым градиентом,
// подсказка свайпа со стрелками (кликабельны — работает и мышью на ПК),
// плитки быстрого доступа с иконкой слева, лента «Какой сейчас вайб?».
// Списков треков на главной НЕТ (решение владельца — навсегда).

function heroSlides(state) {
  return [
    {
      action: "play-recommended",
      mix: "",
      title: "Слушать TG Микс",
      subtitle: "Музыкальные рекомендации для вас",
      button: `<button class="hero-slide__setup" data-action="open-recommendations">${icon("tune")} Настроить</button>`,
      hint: "Проведите, чтобы включить свои треки",
    },
    {
      action: "play-mix",
      mix: "library",
      title: "Слушать мои треки",
      subtitle: state.libraryTotal
        ? "Любимые треки из вашей коллекции"
        : "Добавьте треки в библиотеку",
      button: "",
      hint: "Проведите, чтобы включить TG Микс",
    },
  ];
}

function renderHero(state) {
  const slides = heroSlides(state)
    .map(
      (slide) => `
        <div class="hero-slide" data-action="${slide.action}"${slide.mix ? ` data-mix="${slide.mix}"` : ""}>
          <div class="hero-slide__play">${icon("play")}</div>
          <div class="hero-slide__title">${slide.title}</div>
          <div class="hero-slide__subtitle">${slide.subtitle}</div>
          ${slide.button}
          <div class="hero-slide__hint">
            <button class="hero-arrow" data-action="hero-prev" aria-label="Предыдущий микс">${icon("chevron-left")}</button>
            <span>${slide.hint}</span>
            <button class="hero-arrow" data-action="hero-next" aria-label="Следующий микс">${icon("chevron")}</button>
          </div>
        </div>
      `
    )
    .join("");

  return `
    <div class="hero">
      <div class="hero__track h-scroll" data-role="hero-scroll">${slides}</div>
    </div>
  `;
}

function renderSubscription(state) {
  if (!state.premium || state.premium.active || state.subDismissed) return "";
  // Пока триал не использован — предлагаем его: бесплатное «попробовать»
  // конвертит кратно лучше, чем сразу ценник.
  const trial = state.profile && state.profile.trial_available;
  return `
    <div class="sub-card" data-action="${trial ? "start-trial" : "open-premium"}">
      <button class="sub-card__close" data-action="dismiss-sub" aria-label="Скрыть">${icon("close")}</button>
      <div class="sub-card__title">${trial ? "3 дня Premium бесплатно" : `Целый месяц — ${state.premium.price_rub} ₽`}</div>
      <div class="sub-card__subtitle">${trial ? "Без карты: офлайн, без рекламы, эквалайзер" : "Premium: без рекламы и офлайн"}</div>
      <span class="sub-card__cta">${trial ? "Забрать" : "Подключить"}</span>
    </div>
  `;
}

// Рефералка на главной: заметная точка входа для не-Premium (запрос владельца)
function renderReferralTeaser(state) {
  if (!state.premium || state.premium.active) return "";
  return `
    <button class="ref-teaser" data-action="open-referral">
      <span class="ref-teaser__emoji">🎁</span>
      <span class="ref-teaser__text">
        <span class="ref-teaser__title">Пригласи друга — неделя Premium</span>
        <span class="ref-teaser__sub">Награда приходит сразу, за первого же</span>
      </span>
      ${icon("chevron")}
    </button>
  `;
}

function renderTiles(state) {
  const recentCount = getRecentTracks().length;
  const tiles = [
    {
      action: "open-mytracks",
      ic: "library",
      tone: "magenta",
      title: "Мои треки",
      sub: state.libraryTotal ? `${state.libraryTotal} всего` : "Пока пусто",
    },
    {
      action: "open-recent",
      ic: "history",
      tone: "teal",
      title: "Недавнее",
      sub: recentCount ? "Вы слушали" : "",
    },
    {
      action: "open-playlists",
      ic: "playlist",
      tone: "violet",
      title: "Плейлисты",
      sub: "",
    },
  ];

  const items = tiles
    .map(
      (t) => `
        <button class="vk-tile" data-action="${t.action}">
          <span class="vk-tile__icon vk-tile__icon--${t.tone}">${icon(t.ic)}</span>
          <span class="vk-tile__text">
            <span class="vk-tile__title">${t.title}</span>
            ${t.sub ? `<span class="vk-tile__sub">${t.sub}</span>` : ""}
          </span>
        </button>
      `
    )
    .join("");

  return `<div class="vk-grid">${items}</div>`;
}

// Плейлисты по настроению — серверный микс /mix?mood= (тот же движок, что «Настроить»)
const VIBES = [
  { mood: "love", label: "Любовь", tone: "love" },
  { mood: "happy", label: "Радостно", tone: "happy" },
  { mood: "sad", label: "Грустно", tone: "sad" },
  { mood: "energetic", label: "Активно", tone: "active" },
  { mood: "calm", label: "Спокойно", tone: "calm" },
];

function renderVibes() {
  const cards = VIBES.map(
    (v) => `
      <button class="vibe-card vibe-card--${v.tone}" data-action="play-vibe" data-mood="${v.mood}">
        ${icon("play")}<span>${v.label}</span>
      </button>
    `
  ).join("");

  return `
    <div class="vibe-section">
      <div class="vibe-section__label">Выберите плейлист по настроению</div>
      <div class="vibe-section__title">Какой сейчас вайб?</div>
      <div class="vibe-row h-scroll">${cards}</div>
    </div>
  `;
}

export function renderHome(state) {
  return `
    ${renderHero(state)}
    ${renderSubscription(state)}
    ${renderTiles(state)}
    ${renderVibes()}
    ${renderReferralTeaser(state)}
  `;
}

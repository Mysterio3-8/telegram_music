import { icon } from "../components/icons.js";
import { escapeHtml } from "../components/trackRow.js";
import { isFavoriteArtist } from "../prefs.js";

// Онбординг при первом входе (запрос владельца): знакомим с приложением,
// спрашиваем любимых исполнителей (для рекомендаций), предлагаем импорт музыки.

function renderWelcome() {
  return `
    <div class="onb-hero">
      <div class="onb-hero__logo">🎧</div>
      <div class="onb-hero__title">Добро пожаловать в TG Music</div>
      <div class="onb-hero__sub">Вся музыка в Телеграме: миксы под настроение, поиск, плейлисты, эквалайзер и офлайн</div>
    </div>
    <div class="onb-points">
      <div class="onb-point">${icon("play")}<span>Слушайте бесконечные миксы под ваш вкус</span></div>
      <div class="onb-point">${icon("import")}<span>Переносите плейлисты из Spotify, Яндекса и ВК</span></div>
      <div class="onb-point">${icon("gift")}<span>Зовите друзей — получайте Premium бесплатно</span></div>
    </div>
    <button class="btn btn--primary btn--block" data-action="onb-next">Начать</button>
  `;
}

function renderArtists(state) {
  const artists = state.onbArtists || [];
  if (!artists.length) {
    // Нет данных об исполнителях (пустая база) — пропускаем шаг
    return `
      <div class="onb-step-head">Почти готово</div>
      <div class="onb-step-sub">Отметьте любимых исполнителей позже в настройках — микс станет точнее.</div>
      <button class="btn btn--primary btn--block" data-action="onb-next">Далее</button>
    `;
  }
  const chips = artists
    .map(
      (a) => `
        <button class="onb-chip${isFavoriteArtist(a.name) ? " is-active" : ""}"
          data-action="onb-artist" data-name="${escapeHtml(a.name)}">
          ${escapeHtml(a.name)}
        </button>
      `
    )
    .join("");
  return `
    <div class="onb-step-head">Какие артисты вам нравятся?</div>
    <div class="onb-step-sub">Выберите несколько — подстроим рекомендации под вас</div>
    <div class="onb-chips">${chips}</div>
    <button class="btn btn--primary btn--block" data-action="onb-next">Далее</button>
  `;
}

function renderImport() {
  return `
    <div class="onb-hero">
      <div class="onb-hero__logo">📥</div>
      <div class="onb-hero__title">Перенесите свою музыку</div>
      <div class="onb-hero__sub">Забыли любимые треки в другом сервисе? Перенесём их в TG Music за минуту.</div>
    </div>
    <button class="btn btn--primary btn--block" data-action="onb-import">Перенести из Spotify, Яндекса, ВК</button>
    <button class="btn btn--ghost btn--block" style="margin-top:10px" data-action="onb-finish">Позже, начать слушать</button>
  `;
}

const STEPS = [renderWelcome, renderArtists, renderImport];

export function renderOnboarding(state) {
  const step = state.onbStep || 0;
  const dots = STEPS.map(
    (_, i) => `<span class="onb-dot${i === step ? " is-active" : ""}"></span>`
  ).join("");
  return `
    <div class="onboarding">
      <div class="onb-dots">${dots}</div>
      <div class="onb-body">${STEPS[step](state)}</div>
    </div>
  `;
}

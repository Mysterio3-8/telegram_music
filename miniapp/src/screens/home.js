import { icon } from "../components/icons.js";
import { renderTrackList } from "../components/trackRow.js";

const HOME_LIST_LIMIT = 6;

function greeting(user) {
  const hour = new Date().getHours();
  const timeWord = hour < 5 ? "Доброй ночи" : hour < 12 ? "Доброе утро" : hour < 18 ? "Добрый день" : "Добрый вечер";
  const name = user && user.first_name ? `, ${user.first_name}` : "";
  return `${timeWord}${name}`;
}

export function renderHome(state) {
  const fresh = state.catalog.slice(0, HOME_LIST_LIMIT);
  const premiumBanner =
    state.premium && !state.premium.active
      ? `
        <div class="premium-card" data-action="open-profile">
          <div class="premium-card__icon">${icon("crown")}</div>
          <div>
            <div class="premium-card__title">Premium за ${state.premium.price_rub} ₽</div>
            <div class="premium-card__subtitle">Без рекламы и лимитов — на 30 дней</div>
          </div>
        </div>
      `
      : "";

  return `
    <p class="home-greeting">${greeting(state.user)}</p>

    <div class="mix-hero" data-action="play-all">
      <div class="mix-hero__play">${icon("play")}</div>
      <div class="mix-hero__title">Слушать всё</div>
      <div class="mix-hero__subtitle">${state.catalogTotal} треков в случайном порядке</div>
    </div>

    ${premiumBanner}

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

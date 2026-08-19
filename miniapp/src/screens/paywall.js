import { icon } from "../components/icons.js";

// Пэйвол Mini App (решение владельца): бот бесплатный, приложение — по подписке.
// Первый день бесплатно; дальше 49 ₽/мес. Текст объясняет, за что платят,
// и честно говорит, что цена временная — деньги идут на серверы.

const FEATURES = [
  ["🎛", "Плеер как в больших сервисах", "Очередь, эквалайзер на 7 полос, таймер сна, повтор, тексты песен"],
  ["🎧", "Миксы под настроение", "Infinity Mix собирает подборку под ваш вкус — и не крутит одно и то же"],
  ["🎤", "Карточки артистов", "Фото, жанры, топ треков, альбомы, похожие исполнители, подписка"],
  ["📚", "Библиотека и плейлисты", "Свои плейлисты, «Мои треки», сортировка, поиск по разделам"],
  ["📥", "Офлайн-режим", "Скачивайте треки в приложение и слушайте без интернета"],
  ["🚫", "Без рекламы и без обязательных подписок", "Ничто не отвлекает"],
];

export function renderPaywall(state) {
  const price = (state.premium && state.premium.price_rub) || 49;
  const trialAvailable = state.profile ? state.profile.trial_available : true;

  const features = FEATURES.map(
    ([emoji, title, text]) => `
      <div class="paywall-feature">
        <span class="paywall-feature__emoji">${emoji}</span>
        <span class="paywall-feature__body">
          <span class="paywall-feature__title">${title}</span>
          <span class="paywall-feature__text">${text}</span>
        </span>
      </div>
    `
  ).join("");

  const trialButton = trialAvailable
    ? `<button class="btn btn--primary paywall__cta" data-action="paywall-trial">
         ${icon("sparkles")} Попробовать бесплатно — 1 день
       </button>`
    : "";

  return `
    <div class="paywall">
      <div class="paywall__hero">
        <div class="paywall__badge">Полная версия</div>
        <h1 class="paywall__title">Infinity Music Плеер</h1>
        <p class="paywall__lead">
          Музыка в боте — <b>бесплатно навсегда</b>. Приложение — это уже отдельный
          сервис: плеер, миксы, плейлисты, артисты и офлайн.
        </p>
      </div>

      <div class="paywall__features">${features}</div>

      <div class="paywall__price">
        <div class="paywall__price-value">${price} ₽<span>/месяц</span></div>
        <div class="paywall__price-note">
          Дешевле чашки кофе. Цена временная — пока набираем на серверы,
          потом станет дороже. Отписаться можно в любой момент.
        </div>
      </div>

      ${trialButton}
      <button class="btn ${trialAvailable ? "btn--ghost" : "btn--primary"} paywall__cta" data-action="paywall-buy">
        ${icon("premium")} Открыть за ${price} ₽
      </button>

      <p class="paywall__footer">
        Не хотите платить — просто пользуйтесь ботом: там поиск и скачивание
        музыки без ограничений.
      </p>
    </div>
  `;
}

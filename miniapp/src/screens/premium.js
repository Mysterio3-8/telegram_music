import { icon } from "../components/icons.js";

// Экран Premium с тарифами (ТЗ §24): 1/3/6/12 месяцев, годовой выделен как
// самый выгодный. Цена = базовая цена месяца × месяцы (со скидкой пригласившего).

// months=1200 — тариф «навсегда» (совпадает с FOREVER_MONTHS на бэкенде)
export const FOREVER_MONTHS = 1200;
const FOREVER_PRICE = 10000;

const PLANS = [
  { months: 1, label: "1 месяц" },
  { months: 3, label: "3 месяца" },
  { months: 6, label: "6 месяцев" },
  { months: 12, label: "12 месяцев" },
  { months: FOREVER_MONTHS, label: "Навсегда" },
];

// Плюшки с описанием — чтобы человек видел, за что платит
const PERKS = [
  ["sparkles", "Без рекламы", "Ни баннеров, ни пауз — только музыка"],
  ["download", "Офлайн-режим", "Скачивайте треки и слушайте без интернета"],
  ["import", "Перенос пачкой", "Целые плейлисты и профили из Spotify, Яндекса, ВК и SoundCloud"],
  ["playlist", "Без лимитов", "Сколько угодно плейлистов и загрузок своих треков"],
  ["sliders", "Эквалайзер и таймер сна", "7 полос, 20 пресетов, засыпайте под музыку"],
  ["lyrics", "Тексты песен", "Добавляйте и редактируйте тексты любимых треков"],
  ["gift", "Дни в подарок", "Достижения и друзья приносят ещё больше Premium"],
];

function planPrice(state, months) {
  if (months >= FOREVER_MONTHS) {
    return { full: FOREVER_PRICE, effective: FOREVER_PRICE, discount: 0 };
  }
  const base = state.premium ? state.premium.price_rub : 21;
  const discount = state.premium ? state.premium.discount_pct || 0 : 0;
  const full = base * months;
  const effective = discount ? Math.floor((full * (100 - discount)) / 100) : full;
  return { full, effective, discount };
}

function planCard(state, plan) {
  const { full, effective, discount } = planPrice(state, plan.months);
  const active = state.premiumMonths === plan.months;
  const isYear = plan.months === 12;
  const forever = plan.months >= FOREVER_MONTHS;
  const badge = forever ? "Один раз — навсегда" : isYear ? "Выгоднее всего" : "";
  const monthly =
    !forever && plan.months > 1
      ? `<span class="plan-card__monthly">${Math.round(effective / plan.months)} ₽/мес</span>`
      : forever
        ? '<span class="plan-card__monthly">больше никогда не платить</span>'
        : "";
  return `
    <button class="plan-card${active ? " is-active" : ""}${isYear ? " plan-card--best" : ""}${forever ? " plan-card--forever" : ""}" data-action="premium-plan" data-months="${plan.months}">
      ${badge ? `<span class="plan-card__badge">${badge}</span>` : ""}
      <span class="plan-card__label">${plan.label}</span>
      <span class="plan-card__price">${effective} ₽${discount ? ` <s>${full} ₽</s>` : ""}</span>
      ${monthly}
    </button>
  `;
}

// Бесплатные 3 дня без карты — самый короткий путь к первой оплате
function trialBanner(state) {
  if (!state.profile || !state.profile.trial_available) return "";
  return `
    <div class="trial-banner">
      <div class="trial-banner__title">🎁 3 дня Premium бесплатно</div>
      <div class="trial-banner__sub">Без карты и без автосписаний — просто попробуйте</div>
      <button class="btn btn--primary btn--block" style="margin-top:12px" data-action="start-trial">
        Забрать 3 дня
      </button>
    </div>
  `;
}

export function renderPremium(state) {
  const isActive = state.premium && state.premium.active;
  const { effective } = planPrice(state, state.premiumMonths);

  const perks = PERKS.map(
    ([ic, label, desc]) => `
      <div class="perk-row">
        <span class="perk-row__icon">${icon(ic)}</span>
        <span class="perk-row__text">
          <span class="perk-row__title">${label}</span>
          <span class="perk-row__desc">${desc}</span>
        </span>
      </div>
    `
  ).join("");

  return `
    <div class="page-head" data-role="page-head">
      <button class="icon-btn" data-action="back" aria-label="Назад">${icon("back")}</button>
      <span>TG Music Premium</span>
    </div>

    <div class="premium-hero">
      <div class="premium-hero__icon">${icon("crown")}</div>
      <div class="premium-hero__title">${isActive ? "Premium активен" : "Больше музыки с Premium"}</div>
      ${isActive ? '<div class="premium-hero__sub">Продлите заранее — дни суммируются</div>' : ""}
    </div>

    ${trialBanner(state)}

    <div class="rec-section-label">Что даёт Premium</div>
    <div class="card card--flat">${perks}</div>

    <div class="rec-section-label">Тарифы</div>
    <div class="plan-grid">
      ${PLANS.map((p) => planCard(state, p)).join("")}
    </div>

    <button class="btn btn--primary btn--block" data-action="pay-premium" style="margin-top:16px">
      ${isActive ? "Продлить" : "Оформить"} за ${effective} ₽
    </button>
    <p class="page-hint" style="text-align:center">Оплата картой, СБП или SberPay через ЮKassa. Подписка активируется сразу после оплаты.</p>
  `;
}

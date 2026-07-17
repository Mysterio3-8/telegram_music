import { icon } from "../components/icons.js";

// Экран Premium с тарифами (ТЗ §24): 1/3/6/12 месяцев, годовой выделен как
// самый выгодный. Цена = базовая цена месяца × месяцы (со скидкой пригласившего).

const PLANS = [
  { months: 1, label: "1 месяц" },
  { months: 3, label: "3 месяца" },
  { months: 6, label: "6 месяцев" },
  { months: 12, label: "12 месяцев" },
];

const PERKS = [
  ["sparkles", "Без рекламы"],
  ["download", "Офлайн-прослушивание"],
  ["playlist", "Безлимитные плейлисты и загрузки"],
  ["lyrics", "Добавление текстов песен"],
];

function planPrice(state, months) {
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
  return `
    <button class="plan-card${active ? " is-active" : ""}${isYear ? " plan-card--best" : ""}" data-action="premium-plan" data-months="${plan.months}">
      ${isYear ? '<span class="plan-card__badge">Выгоднее всего</span>' : ""}
      <span class="plan-card__label">${plan.label}</span>
      <span class="plan-card__price">${effective} ₽${discount ? ` <s>${full} ₽</s>` : ""}</span>
      ${plan.months > 1 ? `<span class="plan-card__monthly">${Math.round(effective / plan.months)} ₽/мес</span>` : ""}
    </button>
  `;
}

export function renderPremium(state) {
  const isActive = state.premium && state.premium.active;
  const { effective } = planPrice(state, state.premiumMonths);

  const perks = PERKS.map(
    ([ic, label]) => `
      <div class="settings-row"><div class="settings-row__label">${icon(ic)}${label}</div></div>
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

    <div class="card card--rows">${perks}</div>

    <div class="rec-section-label">Тарифы</div>
    <div class="plan-grid">
      ${PLANS.map((p) => planCard(state, p)).join("")}
    </div>

    <button class="btn btn--primary btn--block" data-action="pay-premium" style="margin-top:16px">
      ${isActive ? "Продлить" : "Оформить"} за ${effective} ₽
    </button>
    <p class="page-hint" style="text-align:center">Оплата через ЮKassa: карта, СБП, SberPay</p>
  `;
}

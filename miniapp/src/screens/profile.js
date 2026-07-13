import { icon } from "../components/icons.js";
import { escapeHtml } from "../components/trackRow.js";

function initials(user) {
  if (!user) return "TG";
  return `${(user.first_name || "")[0] || ""}${(user.last_name || "")[0] || ""}`.toUpperCase() || "TG";
}

function formatUntil(iso) {
  const date = new Date(iso);
  return date.toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit", year: "numeric" });
}

export function renderProfile(state) {
  const user = state.user;
  const premium = state.premium;
  const isPremium = premium && premium.active;
  const name = user
    ? `${user.first_name || ""} ${user.last_name || ""}`.trim() || user.username || "Слушатель"
    : "Слушатель";

  const status = isPremium
    ? `Premium активен до ${formatUntil(premium.until)}`
    : "Бесплатный тариф";

  return `
    <div class="profile-head">
      <button class="icon-btn" data-action="nav" data-screen="home" aria-label="Назад">${icon("back")}</button>
      <span>Профиль</span>
    </div>

    <div class="profile-hero">
      <div class="avatar avatar--lg${isPremium ? " avatar--premium" : ""}">${initials(user)}</div>
      <div class="profile-hero__name">${escapeHtml(name)}</div>
      <div class="profile-hero__status${isPremium ? " is-premium" : ""}">${status}</div>
    </div>

    <div class="premium-card">
      <div class="premium-card__icon">${icon("crown")}</div>
      <div>
        <div class="premium-card__title">${isPremium ? "Вы наш Premium-слушатель" : "Premium-подписка"}</div>
        <div class="premium-card__subtitle">${
          isPremium
            ? "Без рекламы, без лимитов"
            : `Без рекламы и лимитов — ${premium ? premium.price_rub : 21} ₽ / 30 дней`
        }</div>
      </div>
    </div>

    <div class="profile-card">
      <button class="btn btn--primary btn--block" data-action="pay-premium">
        ${isPremium ? "Продлить" : "Оформить"} за ${premium ? premium.price_rub : 21} ₽
      </button>
    </div>
  `;
}

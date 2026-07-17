import { icon } from "../components/icons.js";
import { escapeHtml } from "../components/trackRow.js";

// Профиль (ТЗ §22): аватар из Telegram, без блока «Друзья» и огромной кнопки —
// рефералка живёт в своём разделе (§23), Premium — на экране тарифов (§24).

function initials(user) {
  if (!user) return "TG";
  return `${(user.first_name || "")[0] || ""}${(user.last_name || "")[0] || ""}`.toUpperCase() || "TG";
}

function avatar(user, isPremium) {
  const cls = `avatar avatar--lg${isPremium ? " avatar--premium" : ""}`;
  if (user && user.photo_url) {
    return `<span class="${cls}"><img class="avatar__img" src="${escapeHtml(user.photo_url)}" alt="" /></span>`;
  }
  return `<span class="${cls}">${initials(user)}</span>`;
}

function formatUntil(iso) {
  return new Date(iso).toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit", year: "numeric" });
}

function statTile(value, label) {
  return `
    <div class="pstat">
      <div class="pstat__value">${value}</div>
      <div class="pstat__label">${label}</div>
    </div>
  `;
}

function achievementPreview(profile) {
  const shown = profile.achievements.slice(0, 8);
  const badges = shown
    .map(
      (a) => `<span class="ach-badge${a.unlocked ? " is-unlocked" : ""}" title="${escapeHtml(a.title)}">${a.emoji}</span>`
    )
    .join("");
  return `
    <div class="section-head">
      <span class="section-title">Достижения · ${profile.achievements_unlocked}/${profile.achievements_total}</span>
      <button class="link-more" data-action="open-achievements">Все ${icon("chevron")}</button>
    </div>
    <div class="ach-preview">${badges}</div>
  `;
}

export function renderProfile(state) {
  const user = state.user;
  const name = user
    ? `${user.first_name || ""} ${user.last_name || ""}`.trim() || user.username || "Слушатель"
    : "Слушатель";
  const profile = state.profile;
  const isPremium = profile ? profile.premium.active : state.premium && state.premium.active;
  const rank = profile && profile.referral.rank ? profile.referral.rank : null;

  const head = `
    <div class="page-head" data-role="page-head">
      <button class="icon-btn" data-action="back" aria-label="Назад">${icon("back")}</button>
      <span>Профиль</span>
    </div>
  `;

  const hero = `
    <div class="profile-hero">
      ${avatar(user, isPremium)}
      <div class="profile-hero__name">
        ${escapeHtml(name)}${rank ? ` <span class="rank-badge">${rank.emoji} ${rank.title}</span>` : ""}
      </div>
      <div class="profile-hero__status${isPremium ? " is-premium" : ""}">
        ${
          isPremium && profile && profile.premium.until
            ? `Premium до ${formatUntil(profile.premium.until)}`
            : isPremium
              ? "Premium активен"
              : "Бесплатный тариф"
        }
      </div>
    </div>
  `;

  if (state.profileStatus === "loading" && !profile) {
    return `${head}${hero}<div class="empty-state">Загружаю профиль…</div>`;
  }

  const premiumCard = isPremium
    ? `
      <div class="premium-card">
        <div class="premium-card__icon">${icon("crown")}</div>
        <div>
          <div class="premium-card__title">TG Music Premium активен</div>
          <div class="premium-card__subtitle">Без рекламы и лимитов</div>
        </div>
      </div>
    `
    : `
      <div class="premium-card" data-action="open-premium">
        <div class="premium-card__icon">${icon("crown")}</div>
        <div>
          <div class="premium-card__title">TG Music Premium</div>
          <div class="premium-card__subtitle">от ${state.premium ? state.premium.price_rub : 21} ₽ в месяц</div>
        </div>
      </div>
    `;

  const referralRow = `
    <button class="settings-row" data-action="open-referral" style="width:100%;margin-top:10px">
      <div class="settings-row__label">${icon("gift")}Реферальная программа</div>
      ${icon("chevron")}
    </button>
  `;

  if (!profile) {
    return `${head}${hero}${premiumCard}${referralRow}`;
  }

  return `
    ${head}${hero}

    <div class="pstat-grid pstat-grid--3">
      ${statTile(profile.achievements_unlocked, "Достижений")}
      ${statTile(profile.stats.listens, "Прослушано")}
      ${statTile(profile.stats.streak_days, "Дней подряд")}
    </div>

    ${premiumCard}
    ${referralRow}
    ${achievementPreview(profile)}
  `;
}

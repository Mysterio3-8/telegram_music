import { icon } from "../components/icons.js";
import { escapeHtml } from "../components/trackRow.js";

function initials(user) {
  if (!user) return "TG";
  return `${(user.first_name || "")[0] || ""}${(user.last_name || "")[0] || ""}`.toUpperCase() || "TG";
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

function rankProgress(referral) {
  if (!referral.next_rank) {
    return `<div class="rank-progress__text">Максимальный ранг достигнут 👑</div>`;
  }
  const threshold = referral.invited + referral.to_next;
  const pct = Math.min(100, Math.round((referral.invited / threshold) * 100));
  return `
    <div class="rank-progress__text">
      До ${referral.next_rank.emoji} ${referral.next_rank.title} — ещё ${referral.to_next}
    </div>
    <div class="rank-progress__bar"><span style="width:${pct}%"></span></div>
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
      <button class="icon-btn" data-action="nav" data-screen="home" aria-label="Назад">${icon("back")}</button>
      <span>Профиль</span>
    </div>
  `;

  const hero = `
    <div class="profile-hero">
      <div class="avatar avatar--lg${isPremium ? " avatar--premium" : ""}">${initials(user)}</div>
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

  if (!profile) {
    // профиль не загрузился — показываем базовый премиум-блок
    return `
      ${head}${hero}
      <div class="profile-card">
        <button class="btn btn--primary btn--block" data-action="pay-premium">
          ${isPremium ? "Продлить" : "Оформить"} Premium за ${state.premium ? state.premium.price_rub : 21} ₽
        </button>
      </div>
    `;
  }

  const ref = profile.referral;
  const premium = profile.premium;
  const discountNote =
    premium.discount_pct > 0 && !isPremium
      ? `<div class="premium-card__subtitle">Скидка ${premium.discount_pct}% — ${premium.price_rub_effective} ₽ вместо ${premium.price_rub} ₽</div>`
      : "";

  return `
    ${head}${hero}

    <div class="rank-progress card">
      ${rankProgress(ref)}
    </div>

    <div class="pstat-grid">
      ${statTile(ref.invited, "Друзей")}
      ${statTile(`${profile.achievements_unlocked}`, "Достижений")}
      ${statTile(profile.stats.listens, "Прослушано")}
      ${statTile(profile.stats.streak_days, "Дней подряд")}
    </div>

    <button class="btn btn--primary btn--block" data-action="invite-friend" style="margin-top:16px">
      ${icon("share")} Пригласить друга
    </button>

    <div class="premium-card" style="margin-top:18px" ${isPremium ? "" : 'data-action="pay-premium"'}>
      <div class="premium-card__icon">${icon("crown")}</div>
      <div>
        <div class="premium-card__title">${isPremium ? "TG Music Premium активен" : "TG Music Premium"}</div>
        ${
          isPremium
            ? '<div class="premium-card__subtitle">Без рекламы и лимитов</div>'
            : discountNote ||
              `<div class="premium-card__subtitle">30 дней — ${premium.price_rub} ₽</div>`
        }
      </div>
    </div>

    ${
      isPremium
        ? ""
        : `<div class="profile-card"><button class="btn btn--primary btn--block" data-action="pay-premium">Оформить за ${premium.price_rub_effective ?? premium.price_rub} ₽</button></div>`
    }

    ${achievementPreview(profile)}
  `;
}

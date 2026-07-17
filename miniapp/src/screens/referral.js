import { icon } from "../components/icons.js";
import { escapeHtml } from "../components/trackRow.js";

// Реферальная программа (ТЗ §23): описание, принцип работы, награды, прогресс.
// Пороги наград зеркалят REFERRAL_MILESTONES бэкенда (services/gamification.py).

const REWARDS = [
  { friends: 1, label: "3 дня Premium" },
  { friends: 3, label: "10 дней Premium" },
  { friends: 5, label: "30 дней Premium" },
  { friends: 10, label: "60 дней Premium" },
  { friends: 25, label: "180 дней Premium" },
  { friends: 100, label: "Premium навсегда" },
];

const STEPS = [
  "Поделитесь личной ссылкой с другом",
  "Друг открывает бота по вашей ссылке",
  "Награда начисляется автоматически",
];

function rewardsList(invited) {
  return REWARDS.map((r) => {
    const done = invited >= r.friends;
    return `
      <div class="ref-reward${done ? " is-done" : ""}">
        <span class="ref-reward__check">${icon(done ? "check" : "gift")}</span>
        <span class="ref-reward__friends">${r.friends} ${r.friends === 1 ? "друг" : r.friends < 5 ? "друга" : "друзей"}</span>
        <span class="ref-reward__prize">${r.label}</span>
      </div>
    `;
  }).join("");
}

function progressCard(profile) {
  if (!profile) {
    return '<div class="empty-state">Загружаю данные…</div>';
  }
  const ref = profile.referral;
  const rank = ref.rank;
  const next = ref.next_rank;
  const threshold = next ? ref.invited + ref.to_next : ref.invited || 1;
  const pct = Math.min(100, Math.round((ref.invited / threshold) * 100));

  return `
    <div class="card ref-progress">
      <div class="ref-progress__row">
        <span class="ref-progress__count">${ref.invited}</span>
        <span class="ref-progress__label">приглашено</span>
        ${rank ? `<span class="rank-badge">${rank.emoji} ${rank.title}</span>` : ""}
      </div>
      ${
        next
          ? `<div class="rank-progress__text">До ранга ${next.emoji} ${next.title} — ещё ${ref.to_next}</div>
             <div class="rank-progress__bar"><span style="width:${pct}%"></span></div>`
          : rank
            ? '<div class="rank-progress__text">Максимальный ранг достигнут 👑</div>'
            : ""
      }
    </div>
  `;
}

export function renderReferral(state) {
  const profile = state.profile;
  const link = profile ? profile.referral.link : "";

  const steps = STEPS.map(
    (text, i) => `
      <div class="ref-step">
        <span class="ref-step__num">${i + 1}</span>
        <span class="ref-step__text">${text}</span>
      </div>
    `
  ).join("");

  return `
    <div class="page-head" data-role="page-head">
      <button class="icon-btn" data-action="back" aria-label="Назад">${icon("back")}</button>
      <span>Реферальная программа</span>
    </div>

    <div class="ref-intro">
      <div class="ref-intro__emoji">🎁</div>
      <div class="ref-intro__title">Приглашайте друзей — получайте Premium</div>
      <div class="ref-intro__text">За каждый порог приглашённых начисляются дни Premium. 100 друзей — подписка навсегда. А когда приглашённый друг оплачивает Premium, вы получаете скидку 50% на следующую покупку.</div>
    </div>

    ${progressCard(profile)}

    <div class="rec-section-label">Как это работает</div>
    <div class="card card--rows ref-steps">${steps}</div>

    <div class="rec-section-label">Награды</div>
    <div class="card ref-rewards">${rewardsList(profile ? profile.referral.invited : 0)}</div>

    <div class="rec-actions" style="margin-top:16px">
      ${link ? `<button class="btn btn--ghost" data-action="copy-referral" data-link="${escapeHtml(link)}">${icon("copy")} Скопировать</button>` : ""}
      <button class="btn btn--primary" data-action="invite-friend">${icon("share")} Пригласить</button>
    </div>
  `;
}

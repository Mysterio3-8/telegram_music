import { icon } from "../components/icons.js";
import { escapeHtml } from "../components/trackRow.js";
import { dayWord } from "./achievements.js";

// Реферальная программа (ТЗ §23): описание, принцип работы, награды, прогресс.
// Пороги наград зеркалят REFERRAL_MILESTONES бэкенда (services/gamification.py).

// Пороги приходят с сервера (profile.referral.milestones) — своей копии здесь
// больше нет. Раньше список был захардкожен неурезанными днями, а баннер
// ближайшей награды показывал урезанные: приложение и бот расходились в цифрах.

const STEPS = [
  "Поделитесь личной ссылкой с другом",
  "Друг открывает бота по вашей ссылке",
  "Награда начисляется автоматически",
];

// Верхний порог — «Infinity Premium», а не «36500 дней»: столько дней стоит в
// REFERRAL_MILESTONES как техническая запись «навсегда».
const LIFETIME_DAYS = 36500;

function prizeText(days) {
  return days >= LIFETIME_DAYS ? "Infinity Premium" : `${days} ${dayWord(days)} Premium`;
}

function rewardsList(profile) {
  const milestones = profile && profile.referral.milestones ? profile.referral.milestones : [];
  const invited = profile ? profile.referral.invited : 0;
  return milestones
    .map((r) => {
      const done = invited >= r.friends;
      return `
      <div class="ref-reward${done ? " is-done" : ""}">
        <span class="ref-reward__check">${icon(done ? "check" : "gift")}</span>
        <span class="ref-reward__friends">${r.friends} ${r.friends === 1 ? "друг" : r.friends < 5 ? "друга" : "друзей"}</span>
        <span class="ref-reward__prize">${prizeText(r.days)}</span>
      </div>
    `;
    })
    .join("");
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

// Ближайшая награда крупно: «ещё 1 друг — и +7 дней» работает лучше списка порогов
function nextRewardBanner(profile) {
  if (!profile) return "";
  const { to_next_reward: left, next_reward_days: days } = profile.referral;
  if (!left || !days) return "";
  return `
    <div class="ref-next">
      <div class="ref-next__title">Ещё ${left} ${left === 1 ? "друг" : left < 5 ? "друга" : "друзей"} — и ${prizeText(days)}</div>
      <div class="ref-next__sub">Награда придёт автоматически</div>
    </div>
  `;
}

function leaderboard(state) {
  const rows = state.referralTop || [];
  if (!rows.length) return "";
  const medals = ["🥇", "🥈", "🥉"];
  const items = rows
    .map(
      (row, i) => `
        <div class="leader-row">
          <span class="leader-row__place">${medals[i] || i + 1}</span>
          <span class="leader-row__name">${escapeHtml(row.name)}</span>
          <span class="leader-row__count">${row.invited}</span>
        </div>
      `
    )
    .join("");
  return `
    <div class="rec-section-label">Топ приглашающих</div>
    <div class="card card--flat leader-list">${items}</div>
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

    ${nextRewardBanner(profile)}
    ${progressCard(profile)}
    ${leaderboard(state)}

    <div class="rec-section-label">Как это работает</div>
    <div class="card card--rows ref-steps">${steps}</div>

    <div class="rec-section-label">Награды</div>
    <div class="card ref-rewards">${rewardsList(profile)}</div>

    <div class="rec-actions" style="margin-top:16px">
      ${link ? `<button class="btn btn--ghost" data-action="copy-referral" data-link="${escapeHtml(link)}">${icon("copy")} Скопировать</button>` : ""}
      <button class="btn btn--primary" data-action="invite-friend">${icon("share")} Пригласить</button>
    </div>
  `;
}

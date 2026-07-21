import { icon } from "../components/icons.js";

function achievementCard(a) {
  const pct = a.target ? Math.min(100, Math.round((a.progress / a.target) * 100)) : 0;
  const reward = a.reward_days
    ? `<span class="ach-card__reward">+${a.reward_days} ${dayWord(a.reward_days)} Premium</span>`
    : "";
  return `
    <div class="ach-card${a.unlocked ? " is-unlocked" : ""}">
      <span class="ach-card__emoji">${a.emoji}</span>
      <div class="ach-card__body">
        <div class="ach-card__title">${a.title} ${reward}</div>
        ${
          a.unlocked
            ? '<div class="ach-card__done">Получено</div>'
            : `<div class="ach-card__bar"><span style="width:${pct}%"></span></div>
               <div class="ach-card__progress">${a.progress} / ${a.target}</div>`
        }
      </div>
    </div>
  `;
}

export function dayWord(days) {
  const last = days % 10;
  const two = days % 100;
  if (two >= 11 && two <= 14) return "дней";
  if (last === 1) return "день";
  if (last >= 2 && last <= 4) return "дня";
  return "дней";
}

export function renderAchievements(state) {
  const head = `
    <div class="page-head" data-role="page-head">
      <button class="icon-btn" data-action="back" aria-label="Назад">${icon("back")}</button>
      <span>Достижения</span>
    </div>
  `;

  const profile = state.profile;
  if (!profile) {
    return `${head}<div class="empty-state">Откройте профиль, чтобы загрузить достижения.</div>`;
  }

  const categories = [];
  const byCategory = new Map();
  for (const a of profile.achievements) {
    if (!byCategory.has(a.category)) {
      byCategory.set(a.category, []);
      categories.push(a.category);
    }
    byCategory.get(a.category).push(a);
  }

  const sections = categories
    .map(
      (cat) => `
        <div class="rec-section-label">${cat}</div>
        <div class="ach-list">${byCategory.get(cat).map(achievementCard).join("")}</div>
      `
    )
    .join("");

  const earned = profile.achievements
    .filter((a) => a.unlocked)
    .reduce((sum, a) => sum + (a.reward_days || 0), 0);
  const pending = profile.achievements
    .filter((a) => !a.unlocked)
    .reduce((sum, a) => sum + (a.reward_days || 0), 0);

  return `
    ${head}
    <div class="ach-summary">Открыто ${profile.achievements_unlocked} из ${profile.achievements_total}</div>
    <div class="card card--flat ach-bank">
      <div><b>${earned}</b> ${dayWord(earned)} Premium уже заработано</div>
      ${pending ? `<div class="hint-text">Ещё ${pending} ${dayWord(pending)} ждут — выполняйте достижения</div>` : ""}
    </div>
    ${sections}
  `;
}

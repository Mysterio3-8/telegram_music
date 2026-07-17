import { icon } from "../components/icons.js";

function achievementCard(a) {
  const pct = a.target ? Math.min(100, Math.round((a.progress / a.target) * 100)) : 0;
  return `
    <div class="ach-card${a.unlocked ? " is-unlocked" : ""}">
      <span class="ach-card__emoji">${a.emoji}</span>
      <div class="ach-card__body">
        <div class="ach-card__title">${a.title}</div>
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

  return `
    ${head}
    <div class="ach-summary">Открыто ${profile.achievements_unlocked} из ${profile.achievements_total}</div>
    ${sections}
  `;
}

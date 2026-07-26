import { icon } from "../components/icons.js";
import { escapeHtml } from "../components/trackRow.js";

// Конкурсы (SPEC-2.0 §28): условия, участие, итоги.
// Все условия проверяет сервер — экран только показывает их состояние.

function prizeLabel(contest) {
  if (contest.prize_days === 0) return "Premium навсегда";
  return `${contest.prize_days} дней Premium`;
}

function endsLabel(contest) {
  const date = new Date(contest.ends_at);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString("ru-RU", { day: "numeric", month: "long" });
}

function condition(done, text) {
  return `
    <div class="contest-cond${done ? " is-done" : ""}">
      <span class="contest-cond__mark">${icon(done ? "check" : "plus")}</span>
      <span class="contest-cond__text">${text}</span>
    </div>
  `;
}

function conditions(contest) {
  const rows = [];
  if (contest.channel_url) {
    rows.push(condition(contest.is_subscribed, "Подписаться на наш канал"));
  }
  if (contest.required_referrals > 0) {
    rows.push(
      condition(
        contest.referrals >= contest.required_referrals,
        `Пригласить друзей — ${contest.referrals} из ${contest.required_referrals}`
      )
    );
  }
  return rows.join("");
}

function actionButton(contest) {
  if (contest.joined) {
    return `<div class="contest-joined">${icon("check")} Вы участвуете</div>`;
  }
  if (!contest.is_subscribed && contest.channel_url) {
    return `
      <a class="contest-btn" href="${contest.channel_url}" target="_blank" rel="noopener">
        Подписаться на канал
      </a>
      <button class="contest-btn contest-btn--ghost" data-action="contest-join" data-id="${contest.id}">
        Я подписался
      </button>
    `;
  }
  const blocked = contest.referrals < contest.required_referrals;
  return `
    <button class="contest-btn" data-action="${blocked ? "open-referral" : "contest-join"}" data-id="${contest.id}">
      ${blocked ? "Пригласить друзей" : "Участвовать"}
    </button>
  `;
}

function contestCard(contest) {
  return `
    <div class="contest-card">
      <div class="contest-card__prize">${icon("gift")} ${prizeLabel(contest)}</div>
      <h2 class="contest-card__title">${escapeHtml(contest.title)}</h2>
      <div class="contest-card__meta">
        Итоги ${endsLabel(contest)} · участников: ${contest.participants}
      </div>
      ${contest.description ? `<p class="contest-card__text">${escapeHtml(contest.description)}</p>` : ""}
      <div class="contest-conds">${conditions(contest)}</div>
      <div class="contest-card__actions">${actionButton(contest)}</div>
      <div class="contest-card__note">
        Победителя выбираем случайным образом среди тех, кто выполнил условия.
        Premium активируется автоматически.
      </div>
    </div>
  `;
}

export function renderContests(state) {
  const contests = state.contests;

  if (contests === null || contests === undefined) {
    return `<div class="screen-pad"><div class="empty">Загружаем конкурсы…</div></div>`;
  }

  if (!contests.length) {
    return `
      <div class="screen-pad">
        <div class="empty">
          <div class="empty__title">Сейчас конкурсов нет</div>
          <div class="empty__sub">Загляните позже — разыгрываем Premium регулярно</div>
        </div>
      </div>
    `;
  }

  return `<div class="screen-pad contest-list">${contests.map(contestCard).join("")}</div>`;
}

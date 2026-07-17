import { icon } from "../components/icons.js";

// Настройки рекомендаций (настроение / узнаваемость / язык). Выбор сохраняется
// локально; серверная фильтрация микса под эти параметры — следующий блок.

const MOODS = [
  { id: "happy", ic: "sun", label: "Счастливое" },
  { id: "sad", ic: "moon", label: "Грустное" },
  { id: "energetic", ic: "fire", label: "Энергичное" },
  { id: "calm", ic: "leaf", label: "Спокойное" },
  { id: "love", ic: "heart", label: "Любовь" },
];

const RECOGNIZABILITY = [
  { id: "known", label: "Известные" },
  { id: "unknown", label: "Неизвестные" },
  { id: "new", label: "Новые" },
];

const LANGUAGES = [
  { id: "russian", label: "Русская" },
  { id: "foreign", label: "Зарубежная" },
  { id: "instrumental", label: "Инструментальная" },
];

function moodTile(mood, active) {
  return `
    <button class="mood-tile${active ? " is-active" : ""}" data-action="set-mood" data-value="${mood.id}">
      <span class="mood-tile__icon">${icon(mood.ic)}</span>
      <span class="mood-tile__label">${mood.label}</span>
    </button>
  `;
}

function pill(action, item, active) {
  return `
    <button class="pill${active ? " is-active" : ""}" data-action="${action}" data-value="${item.id}">
      ${item.label}
    </button>
  `;
}

export function renderRecommendations(state) {
  const s = state.recDraft;

  return `
    <div class="page-head" data-role="page-head">
      <button class="icon-btn" data-action="back" aria-label="Назад">${icon("back")}</button>
      <span>Настройки TG MIX</span>
    </div>

    <div class="rec-section-label">Настроение</div>
    <div class="mood-grid h-scroll">
      ${MOODS.map((m) => moodTile(m, s.mood === m.id)).join("")}
    </div>

    <div class="rec-section-label">Тип</div>
    <div class="pill-row">
      ${RECOGNIZABILITY.map((r) => pill("set-recog", r, s.recognizability === r.id)).join("")}
    </div>

    <div class="rec-section-label">Язык музыки</div>
    <div class="pill-row">
      ${LANGUAGES.map((l) => pill("set-lang", l, s.language === l.id)).join("")}
    </div>

    <div class="rec-actions">
      <button class="btn btn--ghost" data-action="clear-rec">Очистить</button>
      <button class="btn btn--primary" data-action="apply-rec">Применить</button>
    </div>
  `;
}

import { icon } from "../components/icons.js";
import { getUiSettings } from "../prefs.js";

// «Интерфейс» по скрину VK (копи/ photo_19): акцентный цвет + тактильная
// обратная связь. Тема одна — тёмная (решение владельца), переключателя нет.

export const ACCENTS = [
  { id: "gold", label: "Золотой", color: "#f5a623" },
  { id: "pink", label: "Розовый", color: "#ef3f7f" },
  { id: "green", label: "Люминесцентный зелёный", color: "#32d74b" },
  { id: "azure", label: "Лазурный", color: "#32ade6" },
  { id: "blue", label: "Синий", color: "#3b7bfe" },
];

export function renderInterface() {
  const ui = getUiSettings();
  const rows = ACCENTS.map(
    (accent) => `
      <button class="sheet-item" data-action="set-accent" data-value="${accent.id}">
        <span style="flex:1;text-align:left;color:${accent.color};font-weight:700">${accent.label}</span>
        ${ui.accent === accent.id ? icon("check") : ""}
      </button>
    `
  ).join("");

  return `
    <div class="page-head" data-role="page-head">
      <button class="icon-btn" data-action="back" aria-label="Назад">${icon("back")}</button>
      <span>Интерфейс</span>
    </div>
    <div class="rec-section-label">Акцентный цвет</div>
    <div class="hint-text">С любимым цветом интерфейс удобнее и краше</div>
    <div class="card card--rows">${rows}</div>
    <div class="settings-row" style="width:100%;margin-top:14px">
      <div class="settings-row__label">
        <div>
          Тактильная обратная связь
          <div class="hint-text">Почувствуйте работу приложения кончиками пальцев</div>
        </div>
      </div>
      <button class="switch${ui.haptic ? " is-on" : ""}" data-action="toggle-haptic" aria-label="Тактильная обратная связь"></button>
    </div>
  `;
}

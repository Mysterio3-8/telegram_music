import { icon } from "../components/icons.js";

export function renderSettings(state) {
  const isLight = state.theme === "light";

  return `
    <div class="profile-head">
      <button class="icon-btn" data-action="nav" data-screen="home" aria-label="Назад">${icon("back")}</button>
      <span>Настройки</span>
    </div>

    <div class="card card--rows">
      <div class="settings-row">
        <div class="settings-row__label">${icon("theme")}Светлая тема</div>
        <button class="switch${isLight ? " is-on" : ""}" data-action="theme-toggle" aria-label="Переключить тему"></button>
      </div>
    </div>

    <div class="card card--rows">
      <button class="settings-row" data-action="open-bot" style="width:100%">
        <div class="settings-row__label">${icon("help")}Помощь — написать боту</div>
        ${icon("chevron")}
      </button>
    </div>
  `;
}

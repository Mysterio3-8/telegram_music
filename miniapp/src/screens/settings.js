import { icon } from "../components/icons.js";

function navRow(label, ic, action, data = "") {
  return `
    <button class="settings-row" data-action="${action}"${data} style="width:100%">
      <div class="settings-row__label">${icon(ic)}${label}</div>
      ${icon("chevron")}
    </button>
  `;
}

export function renderSettings(state) {
  const isLight = state.theme === "light";

  return `
    <div class="page-head" data-role="page-head">
      <button class="icon-btn" data-action="nav" data-screen="home" aria-label="Назад">${icon("back")}</button>
      <span>Настройки</span>
    </div>

    <div class="rec-section-label">Интерфейс</div>
    <div class="card card--rows">
      <div class="settings-row">
        <div class="settings-row__label">${icon("theme")}Светлая тема</div>
        <button class="switch${isLight ? " is-on" : ""}" data-action="theme-toggle" aria-label="Переключить тему"></button>
      </div>
    </div>

    <div class="rec-section-label">Предпочтения</div>
    <div class="card card--rows">
      ${navRow("Любимые исполнители", "mic", "open-artists")}
      ${navRow("Настроить рекомендации", "tune", "open-recommendations")}
    </div>

    <div class="rec-section-label">Помощь</div>
    <div class="card card--rows">
      ${navRow("Вопросы и ответы", "help", "open-doc", ' data-doc="faq"')}
      ${navRow("Написать боту", "bell", "open-bot")}
    </div>

    <div class="rec-section-label">Документы</div>
    <div class="card card--rows">
      ${navRow("Политика конфиденциальности", "lock", "open-doc", ' data-doc="privacy"')}
      ${navRow("Лицензионное соглашение", "doc", "open-doc", ' data-doc="license"')}
      ${navRow("О приложении", "sparkles", "open-doc", ' data-doc="about"')}
    </div>
  `;
}

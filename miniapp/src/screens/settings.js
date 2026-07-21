import { icon } from "../components/icons.js";

// Настройки по референсу VK Music (ТЗ §16, §21): секции строк, «Поддержка
// Telegram» вместо «Написать боту», версия — внутри «О приложении».

function navRow(label, ic, action, data = "") {
  return `
    <button class="settings-row" data-action="${action}"${data} style="width:100%">
      <div class="settings-row__label">${icon(ic)}${label}</div>
      ${icon("chevron")}
    </button>
  `;
}

export function renderSettings(state) {
  return `
    <div class="page-head" data-role="page-head">
      <button class="icon-btn" data-action="back" aria-label="Назад">${icon("back")}</button>
      <span>Настройки</span>
    </div>

    <div class="rec-section-label">Музыка</div>
    <div class="card card--rows">
      ${navRow("Настройки TG MIX", "tune", "open-recommendations")}
      ${navRow("Любимые исполнители", "mic", "open-artists")}
      ${navRow("Эквалайзер", "sliders", "open-equalizer")}
    </div>

    <div class="rec-section-label">Приложение</div>
    <div class="card card--rows">
      ${navRow("Интерфейс", "palette", "open-interface")}
      ${navRow("Память устройства", "database", "open-storage")}
    </div>

    <div class="rec-section-label">Подписка</div>
    <div class="card card--rows">
      ${navRow("TG Music Premium", "crown", "open-premium")}
      ${navRow("Реферальная программа", "gift", "open-referral")}
    </div>

    <div class="rec-section-label">Помощь</div>
    <div class="card card--rows">
      ${navRow("Вопросы и ответы", "help", "open-doc", ' data-doc="faq"')}
      ${navRow("Поддержка Telegram", "headset", "open-support")}
    </div>

    <div class="rec-section-label">Документы</div>
    <div class="card card--rows">
      ${navRow("Политика конфиденциальности", "lock", "open-doc", ' data-doc="privacy"')}
      ${navRow("Лицензионное соглашение", "doc", "open-doc", ' data-doc="license"')}
      ${navRow("О приложении", "sparkles", "open-doc", ' data-doc="about"')}
    </div>
  `;
}

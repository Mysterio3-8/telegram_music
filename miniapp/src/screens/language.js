import { icon } from "../components/icons.js";
import { LANGUAGES, getLanguage, isTranslated, t } from "../i18n.js";

// Экран выбора языка (заготовка мультиязычности). Языки без перевода видны в
// списке, но помечены — человек сразу понимает, что увидит английский.

export function renderLanguage() {
  const current = getLanguage();
  const rows = LANGUAGES.map((item) => {
    const pending = isTranslated(item.code)
      ? ""
      : `<div class="settings-row__hint">${t("language.pending")}</div>`;
    return `
      <button class="settings-row" data-action="set-language" data-code="${item.code}" style="width:100%">
        <div class="settings-row__label">
          <span class="lang-flag">${item.flag}</span>
          <span>${item.title}${pending}</span>
        </div>
        ${item.code === current ? icon("check") : ""}
      </button>
    `;
  }).join("");

  return `
    <div class="page-head" data-role="page-head">
      <button class="icon-btn" data-action="back" aria-label="${t("common.back")}">${icon("back")}</button>
      <span>${t("language.title")}</span>
    </div>
    <p class="muted" style="padding:0 16px 12px">${t("language.hint")}</p>
    <div class="card card--rows">${rows}</div>
  `;
}

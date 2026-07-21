import { icon } from "../components/icons.js";
import {
  EQ_FREQS,
  EQ_MAX_DB,
  EQ_MIN_DB,
  EQ_PRESETS,
  currentGains,
  eqSupported,
  getEqSettings,
} from "../equalizer.js";

// Эквалайзер по скринам VK (копи/): тумблер, 7 вертикальных полос, пресеты.

function freqLabel(freq) {
  return freq >= 1000 ? `${freq / 1000} кГц`.replace(".", ",") : `${freq} Гц`;
}

function renderBands(settings) {
  const gains = currentGains(settings);
  const bands = EQ_FREQS.map(
    (freq, i) => `
      <div class="eq-band">
        <div class="eq-band__slider">
          <input type="range" min="${EQ_MIN_DB}" max="${EQ_MAX_DB}" step="1"
            value="${gains[i] || 0}" data-role="eq-band" data-band="${i}"
            ${settings.enabled ? "" : "disabled"} />
        </div>
        <span class="eq-band__label">${freqLabel(freq)}</span>
      </div>
    `
  ).join("");
  return `<div class="eq-bands${settings.enabled ? "" : " is-disabled"}">${bands}</div>`;
}

function renderPresets(settings) {
  const rows = EQ_PRESETS.map(
    (preset) => `
      <button class="sheet-item" data-action="eq-preset" data-value="${preset.id}">
        <span style="flex:1;text-align:left">${preset.label}</span>
        ${settings.preset === preset.id ? icon("check") : ""}
      </button>
    `
  ).join("");
  return `<div class="card card--rows">${rows}</div>`;
}

export function renderEqualizer() {
  const settings = getEqSettings();
  if (!eqSupported()) {
    return `
      <div class="page-head" data-role="page-head">
        <button class="icon-btn" data-action="back" aria-label="Назад">${icon("back")}</button>
        <span>Эквалайзер</span>
      </div>
      <div class="empty-state">Эквалайзер не поддерживается этим устройством.</div>
    `;
  }
  return `
    <div class="page-head" data-role="page-head">
      <button class="icon-btn" data-action="back" aria-label="Назад">${icon("back")}</button>
      <span>Эквалайзер</span>
    </div>
    <div class="settings-row" style="width:100%">
      <div class="settings-row__label">Включить эквалайзер</div>
      <button class="switch${settings.enabled ? " is-on" : ""}" data-action="eq-toggle" aria-label="Эквалайзер"></button>
    </div>
    ${renderBands(settings)}
    ${renderPresets(settings)}
  `;
}

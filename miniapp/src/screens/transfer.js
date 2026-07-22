import { icon } from "../components/icons.js";

// «Перенос из других сервисов» по скрину VK (копи/ photo_16): выбор сервиса,
// поле для ссылки/списка, объяснение как это работает.

const SERVICES = [
  {
    id: "spotify",
    label: "Spotify",
    hint: "Ссылка на плейлист",
    tone: "spotify",
    prompt: "Скопируйте ссылку на свой плейлист в Spotify",
    help: "Откройте плейлист в Spotify → «…» → «Поделиться» → «Копировать ссылку».",
    warn: "Плейлист должен быть публичным — проверьте настройки приватности.",
  },
  {
    id: "yandex",
    label: "Яндекс",
    hint: "Ссылка на плейлист",
    tone: "yandex",
    prompt: "Скопируйте ссылку на свой плейлист в Яндекс Музыке",
    help: "Откройте плейлист в Яндекс Музыке → «Поделиться» → «Скопировать ссылку».",
    warn: "Плейлист должен быть публичным — проверьте настройки приватности.",
  },
  {
    id: "vk",
    label: "ВКонтакте",
    hint: "Список текстом",
    tone: "vk",
    prompt: "Вставьте список треков — по строке на трек",
    help: "ВКонтакте не отдаёт плейлисты без входа. Скопируйте названия треков и вставьте строками «Артист — Название».",
    warn: "",
  },
  {
    id: "soundcloud",
    label: "SoundCloud",
    hint: "Профиль, трек или сет",
    tone: "sc",
    prompt: "Скопируйте ссылку на трек, профиль или сет SoundCloud",
    help: "SoundCloud скачивается напрямую — принимаем ссылку на трек, профиль, лайки или сет.",
    warn: "",
  },
];

export function renderTransfer(state) {
  const cards = SERVICES.map(
    (service) => `
      <button class="transfer-card transfer-card--${service.tone}${state.transferService === service.id ? " is-active" : ""}"
        data-action="transfer-service" data-value="${service.id}">
        <span class="transfer-card__logo">${service.label[0]}</span>
        <span class="transfer-card__label">${service.label}</span>
        <span class="transfer-card__hint">${service.hint}</span>
      </button>
    `
  ).join("");

  const active = SERVICES.find((s) => s.id === state.transferService) || SERVICES[0];
  const isVk = active.id === "vk";
  const placeholder = isVk
    ? "Kizaru — Fendi&#10;Big Baby Tape — Gimme the Loot"
    : "https://…";

  return `
    <div class="page-head" data-role="page-head">
      <button class="icon-btn" data-action="back" aria-label="Назад">${icon("back")}</button>
      <span>Перенос музыки</span>
    </div>

    <div class="transfer-hero">
      <div class="transfer-hero__title">Перенесите плейлисты из других сервисов</div>
      <div class="transfer-hero__sub">Слушайте любимые треки в TG Music</div>
    </div>

    <div class="rec-section-label">Откуда перенести?</div>
    <div class="transfer-grid">${cards}</div>

    <div class="transfer-prompt">${active.prompt}</div>
    <textarea class="transfer-input" data-role="transfer-input" rows="${isVk ? 4 : 2}"
      placeholder="${placeholder}">${state.transferSource || ""}</textarea>
    <div class="hint-text">${active.help}</div>
    ${active.warn ? `<div class="transfer-warn">${active.warn}</div>` : ""}

    <button class="btn btn--primary btn--block" style="margin-top:14px" data-action="transfer-start">
      ${state.transferStatus === "loading" ? "Переношу…" : "Перенести"}
    </button>

    ${state.transferResult ? `<div class="card card--flat transfer-result">${state.transferResult}</div>` : ""}

    <div class="rec-section-label">Как это работает</div>
    <div class="card card--rows transfer-steps">
      <div class="settings-row"><div class="settings-row__label">1. Находим ваши треки в нашей базе — они появляются сразу</div></div>
      <div class="settings-row"><div class="settings-row__label">2. Чего нет — загружаем из открытых источников</div></div>
      <div class="settings-row"><div class="settings-row__label">3. Пришлём отчёт в чат, когда закончим</div></div>
    </div>
  `;
}

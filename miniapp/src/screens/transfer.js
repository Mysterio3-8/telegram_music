import { icon } from "../components/icons.js";
import { escapeHtml } from "../components/trackRow.js";

// «Перенос музыки». Владелец 22.09: «работает только по ссылке, через ВК также,
// не построчно и так далее только ссылка, и убери надписи как это работает и тд
// оставь только, пришлите ссылку». Поэтому здесь ровно три вещи: откуда,
// поле для ссылки и кнопка. Разбор списка строками сервер по-прежнему понимает —
// он просто больше не предлагается на экране.

const SERVICES = [
  { id: "spotify", label: "Spotify", tone: "spotify" },
  { id: "yandex", label: "Яндекс", tone: "yandex" },
  { id: "vk", label: "ВКонтакте", tone: "vk" },
  { id: "soundcloud", label: "SoundCloud", tone: "sc" },
];

export function renderTransfer(state) {
  const cards = SERVICES.map(
    (service) => `
      <button class="transfer-card transfer-card--${service.tone}${state.transferService === service.id ? " is-active" : ""}"
        data-action="transfer-service" data-value="${service.id}">
        <span class="transfer-card__logo">${service.label[0]}</span>
        <span class="transfer-card__label">${service.label}</span>
      </button>
    `
  ).join("");

  return `
    <div class="page-head" data-role="page-head">
      <button class="icon-btn" data-action="back" aria-label="Назад">${icon("back")}</button>
      <span>Перенос музыки</span>
    </div>

    <div class="transfer-hero">
      <div class="transfer-hero__title">Перенесите плейлисты из других сервисов</div>
      <div class="transfer-hero__sub">Слушайте любимые треки в Infinity Music</div>
    </div>

    <div class="rec-section-label">Откуда перенести?</div>
    <div class="transfer-grid">${cards}</div>

    <div class="transfer-prompt">Пришлите ссылку на плейлист</div>
    <textarea class="transfer-input" data-role="transfer-input" rows="2"
      placeholder="https://…">${escapeHtml(state.transferSource || "")}</textarea>

    <button class="btn btn--primary btn--block" style="margin-top:14px" data-action="transfer-start">
      ${state.transferStatus === "loading" ? "Переношу…" : "Перенести"}
    </button>

    ${state.transferResult ? `<div class="card card--flat transfer-result">${state.transferResult}</div>` : ""}
  `;
}

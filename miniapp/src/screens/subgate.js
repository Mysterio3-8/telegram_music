import { icon } from "../components/icons.js";
import { escapeHtml } from "../components/trackRow.js";

// Гейт обязательной подписки (блок B): показывается поверх всего, если пользователь
// не подписан на обязательные каналы и у него нет Premium. Кнопки каналов + «Я
// подписался» (перепроверка) + «Убрать подписки» (Premium снимает ОП).
export function renderSubGate(state) {
  const gate = state.subGate;
  if (!gate) return "";
  const channels = gate.channels
    .filter((c) => c.url)
    .map(
      (c) => `
      <a class="btn btn--primary sub-gate__channel${c.subscribed ? " is-done" : ""}"
         href="${escapeHtml(c.url)}" target="_blank" rel="noopener"
         data-action="sub-click" data-cid="${c.id}">
        ${c.subscribed ? icon("check") : icon("bell")} ${escapeHtml(c.label)}
      </a>`
    )
    .join("");
  return `
    <div class="sub-gate">
      <div class="sub-gate__icon">${icon("note")}</div>
      <h1 class="sub-gate__title">Подпишитесь, чтобы слушать</h1>
      <p class="sub-gate__text">
        TG Music бесплатен, пока вы подписаны на наши каналы.
        Оформите Premium — и обязательные подписки больше не нужны.
      </p>
      <div class="sub-gate__channels">${channels}</div>
      <button class="btn btn--primary sub-gate__check" data-action="sub-recheck">Я подписался</button>
      <button class="btn btn--ghost" data-action="sub-premium">Убрать подписки — Premium</button>
    </div>
  `;
}

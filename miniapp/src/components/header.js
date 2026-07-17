import { icon } from "./icons.js";

function initials(user) {
  if (!user) return "TG";
  const first = (user.first_name || "").trim();
  const last = (user.last_name || "").trim();
  const letters = `${first[0] || ""}${last[0] || ""}`.toUpperCase();
  return letters || (user.username || "TG").slice(0, 2).toUpperCase();
}

export function renderHeader(state) {
  const premium = state.premium && state.premium.active;
  const user = state.user;
  const face = user && user.photo_url
    ? `<img class="avatar__img" src="${user.photo_url}" alt="" />`
    : initials(user);
  return `
    <header class="header">
      <button class="icon-btn" data-action="open-settings" aria-label="Настройки">${icon("settings")}</button>
      <div class="brand"><span class="brand__tg">TG</span><span class="brand__music">MUSIC</span></div>
      <button class="avatar${premium ? " avatar--premium" : ""}" data-action="open-profile" aria-label="Профиль">${face}</button>
    </header>
  `;
}

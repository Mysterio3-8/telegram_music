import { icon } from "./icons.js";

const ITEMS = [
  { id: "home", label: "Главная", icon: "home" },
  { id: "search", label: "Поиск", icon: "search" },
  { id: "library", label: "Библиотека", icon: "library" },
];

export function renderBottomNav(activeScreen) {
  const items = ITEMS.map((item) => {
    const active = item.id === activeScreen;
    return `
      <button class="nav-item${active ? " is-active" : ""}" data-action="nav" data-screen="${item.id}">
        ${icon(item.icon)}
        <span>${item.label}</span>
      </button>
    `;
  }).join("");

  return `
    <nav class="bottom-nav">
      <div class="bottom-nav__inner">${items}</div>
    </nav>
  `;
}

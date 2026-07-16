import { icon } from "../components/icons.js";
import { escapeHtml } from "../components/trackRow.js";

// Кураторские подборки — публичные плейлисты команды сервиса (админов).
export function renderCurators(state) {
  const head = `
    <div class="page-head" data-role="page-head">
      <button class="icon-btn" data-action="nav" data-screen="library" aria-label="Назад">${icon("back")}</button>
      <span>Кураторы</span>
    </div>
  `;

  if (state.curatorsStatus === "loading") {
    return `${head}<div class="empty-state">Загружаю…</div>`;
  }

  const curators = state.curators || [];
  if (!curators.length) {
    return `${head}<div class="empty-state">Кураторские подборки скоро появятся — команда уже собирает первые.</div>`;
  }

  const rows = curators
    .map(
      (p) => `
        <button class="quick-tile" data-action="open-curator" data-id="${p.id}" data-title="${escapeHtml(p.title)}">
          <span class="quick-tile__icon">${icon("star")}</span>
          <span class="quick-tile__text">
            <span class="quick-tile__title">${escapeHtml(p.title)}</span>
            <span class="quick-tile__sub">${p.track_count} треков · подборка команды</span>
          </span>
        </button>
      `
    )
    .join("");

  return `${head}<div class="quick-access">${rows}</div>`;
}

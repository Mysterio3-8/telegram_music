import { icon } from "../components/icons.js";
import { offlineTracks } from "../offline.js";

// «Память устройства» по скрину VK (копи/ photo_15): очистка скачанных треков.
// Скачанные живут в Cache API + индекс в localStorage (offline.js).

export function renderStorage() {
  const count = offlineTracks().length;
  return `
    <div class="page-head" data-role="page-head">
      <button class="icon-btn" data-action="back" aria-label="Назад">${icon("back")}</button>
      <span>Память устройства</span>
    </div>
    <div class="rec-section-label">Память устройства</div>
    <div class="settings-row" style="width:100%">
      <div class="settings-row__label">
        <div>
          Удалить загруженные треки
          <div class="hint-text">Удалите всю скачанную музыку — раздел «Скачанные» будет очищен</div>
        </div>
      </div>
      <span class="hint-text">${count}</span>
    </div>
    <button class="btn btn--ghost btn--block" style="margin-top:12px${count ? "" : ";opacity:.5"}"
      data-action="clear-offline" ${count ? "" : "disabled"}>
      🗑 Удалить скачанные треки
    </button>
  `;
}

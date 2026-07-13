import { renderTrackList } from "../components/trackRow.js";

export function renderLibrary(state) {
  const { libraryPageItems, libraryTotal } = state;
  const shown = libraryPageItems.length;

  if (!libraryTotal) {
    return `
      <div class="lib-row"><span class="section-title">Мои треки</span></div>
      <div class="empty-state">
        Библиотека пуста.<br />Добавляйте треки кнопкой «+» из поиска.
      </div>
    `;
  }

  return `
    <div class="lib-row">
      <span class="section-title">Мои треки · ${libraryTotal}</span>
    </div>
    <div class="card">
      ${renderTrackList(libraryPageItems, { context: "library", state })}
    </div>
    ${
      shown < libraryTotal
        ? '<button class="btn btn--ghost btn--block" style="margin-top:12px" data-action="library-more">Показать ещё</button>'
        : ""
    }
  `;
}

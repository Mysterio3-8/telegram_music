import { icon } from "../components/icons.js";
import { escapeHtml } from "../components/trackRow.js";

// Загрузка своего трека из Mini App (запрос владельца: грузить и через мини-апку).
// Исполнитель обязателен — иначе трек уйдёт как «Неизвестный».

export function renderUpload(state) {
  const u = state.upload || {};
  const fileName = u.fileName ? escapeHtml(u.fileName) : "";
  const busy = u.status === "loading";

  return `
    <div class="page-head" data-role="page-head">
      <button class="icon-btn" data-action="back" aria-label="Назад">${icon("back")}</button>
      <span>Загрузить трек</span>
    </div>

    <div class="rec-section-label">Аудиофайл</div>
    <label class="upload-drop">
      <input type="file" accept="audio/*" data-role="upload-file" hidden />
      <span class="upload-drop__icon">${icon("import")}</span>
      <span class="upload-drop__text">${fileName || "Выберите аудиофайл (MP3, M4A…)"}</span>
    </label>

    <div class="rec-section-label">Название</div>
    <input class="transfer-input" data-role="upload-title" placeholder="Название трека"
      value="${escapeHtml(u.title || "")}" />

    <div class="rec-section-label">Исполнитель <span class="req-mark">обязательно</span></div>
    <input class="transfer-input" data-role="upload-artist" placeholder="Имя исполнителя"
      value="${escapeHtml(u.artist || "")}" />

    <button class="btn btn--primary btn--block" style="margin-top:16px"
      data-action="upload-submit" ${busy ? "disabled" : ""}>
      ${busy ? "Загружаю…" : "Добавить в библиотеку"}
    </button>

    ${u.result ? `<div class="card card--flat transfer-result">${u.result}</div>` : ""}

    <div class="hint-text" style="margin-top:14px">
      Трек попадёт в вашу библиотеку и общий поиск. Указывайте исполнителя —
      без него трек будет «Неизвестным» и потеряется в базе.
    </div>
  `;
}

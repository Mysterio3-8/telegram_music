import { icon } from "../components/icons.js";
import { escapeHtml } from "../components/trackRow.js";

const SOURCE_LABEL = { lrclib: "найдено автоматически", user: "добавлено слушателями", admin: "проверено" };

function editor(state, initial) {
  return `
    <textarea class="lyrics-input" data-role="lyrics-input" rows="12"
      placeholder="Вставьте текст песни построчно…">${escapeHtml(initial)}</textarea>
    <div class="rec-actions">
      ${
        state.lyrics && state.lyrics.found
          ? '<button class="btn btn--ghost" data-action="lyrics-cancel">Отмена</button>'
          : ""
      }
      <button class="btn btn--primary" data-action="lyrics-save">Сохранить</button>
    </div>
  `;
}

export function renderLyrics(state) {
  const track = state.lyricsTrack;
  const title = track ? `${track.artist} — ${track.title}` : "Текст песни";

  const head = `
    <div class="page-head" data-role="page-head">
      <button class="icon-btn" data-action="lyrics-back" aria-label="Назад">${icon("back")}</button>
      <span>Текст песни</span>
    </div>
    <div class="lyrics-track">${escapeHtml(title)}</div>
  `;

  if (state.lyricsStatus === "loading") {
    return `${head}<div class="empty-state">Ищу текст…</div>`;
  }

  const lyrics = state.lyrics;

  if (state.lyricsEditing) {
    return `${head}${editor(state, lyrics && lyrics.text ? lyrics.text : "")}`;
  }

  if (lyrics && lyrics.found) {
    return `
      ${head}
      <pre class="lyrics-text">${escapeHtml(lyrics.text)}</pre>
      <div class="lyrics-meta">${SOURCE_LABEL[lyrics.source] || ""}</div>
      <button class="btn btn--ghost btn--block" data-action="lyrics-edit" style="margin-top:12px">
        ${icon("lyrics")} Предложить правку
      </button>
    `;
  }

  return `
    ${head}
    <p class="page-hint">Текста пока нет. Добавьте его — он появится для всех слушателей.</p>
    ${editor(state, "")}
  `;
}

import { icon } from "../components/icons.js";
import { escapeHtml } from "../components/trackRow.js";

// Текст песни (ТЗ §8): открывается сразу, дизайн по VK — крупный читаемый текст.
// Добавлять и править тексты могут только админы (решение владельца 19.09):
// текст общий для всех слушателей, правка перезаписывает его целиком.

const SOURCE_LABEL = { lrclib: "найдено автоматически", user: "добавлено слушателями", admin: "добавлено администратором" };

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
  // Право правки сообщает сервер — он же его и проверяет при сохранении
  const canEdit = Boolean(state.lyrics && state.lyrics.can_edit);

  const head = `
    <div class="page-head" data-role="page-head">
      <button class="icon-btn" data-action="back" aria-label="Назад">${icon("back")}</button>
      <span>Текст песни</span>
    </div>
    ${
      track
        ? `<div class="lyrics-track">
             <div class="lyrics-track__title">${escapeHtml(track.title)}</div>
             <div class="lyrics-track__artist">${escapeHtml(track.artist)}</div>
           </div>`
        : ""
    }
  `;

  if (state.lyricsStatus === "loading") {
    return `${head}<div class="empty-state">Ищу текст…</div>`;
  }

  const lyrics = state.lyrics;

  if (state.lyricsEditing && canEdit) {
    return `${head}${editor(state, lyrics && lyrics.text ? lyrics.text : "")}`;
  }

  if (lyrics && lyrics.found) {
    return `
      ${head}
      <pre class="lyrics-text">${escapeHtml(lyrics.text)}</pre>
      <div class="lyrics-meta">${SOURCE_LABEL[lyrics.source] || ""}</div>
      ${
        canEdit
          ? `<button class="btn btn--ghost btn--block" data-action="lyrics-edit" style="margin-top:12px">${icon("pencil")} Изменить текст</button>`
          : ""
      }
    `;
  }

  return `
    ${head}
    <p class="page-hint">Текста этой песни пока нет в базе.</p>
    ${canEdit ? editor(state, "") : ""}
  `;
}

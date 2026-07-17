import { icon } from "../components/icons.js";
import { escapeHtml } from "../components/trackRow.js";

// Текст песни (ТЗ §8): открывается сразу, дизайн по VK — крупный читаемый текст.
// Добавление/правка своего текста — только Premium.

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

function premiumNote() {
  return `
    <div class="premium-card" data-action="open-premium" style="margin-top:14px">
      <div class="premium-card__icon">${icon("crown")}</div>
      <div>
        <div class="premium-card__title">Добавление текста — Premium</div>
        <div class="premium-card__subtitle">Оформите подписку, чтобы добавлять свои тексты</div>
      </div>
    </div>
  `;
}

export function renderLyrics(state) {
  const track = state.lyricsTrack;
  const isPremium = state.premium && state.premium.active;

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

  if (state.lyricsEditing && isPremium) {
    return `${head}${editor(state, lyrics && lyrics.text ? lyrics.text : "")}`;
  }

  if (lyrics && lyrics.found) {
    return `
      ${head}
      <pre class="lyrics-text">${escapeHtml(lyrics.text)}</pre>
      <div class="lyrics-meta">${SOURCE_LABEL[lyrics.source] || ""}</div>
      ${
        isPremium
          ? `<button class="btn btn--ghost btn--block" data-action="lyrics-edit" style="margin-top:12px">${icon("pencil")} Предложить правку</button>`
          : ""
      }
    `;
  }

  return `
    ${head}
    <p class="page-hint">Текста этой песни пока нет в базе.</p>
    ${isPremium ? editor(state, "") : premiumNote()}
  `;
}

import { icon } from "../components/icons.js";
import { renderTrackList } from "../components/trackRow.js";
import { offlineTracks, offlineSupported } from "../offline.js";

export function renderDownloads(state) {
  const tracks = offlineTracks();
  const head = `
    <div class="page-head" data-role="page-head">
      <button class="icon-btn" data-action="nav" data-screen="library" aria-label="Назад">${icon("back")}</button>
      <span>Загрузки</span>
    </div>
  `;

  if (!offlineSupported()) {
    return `${head}<div class="empty-state">Офлайн-сохранение недоступно в этом клиенте.</div>`;
  }
  if (!tracks.length) {
    return `
      ${head}
      <p class="page-hint">Сохраняйте треки офлайн через «Ещё» → «Сохранить офлайн» (нужен Premium). Они играют мгновенно и без повторной загрузки.</p>
    `;
  }

  return `
    ${head}
    <div class="card home-track-card">${renderTrackList(tracks, { context: "offline", state })}</div>
  `;
}

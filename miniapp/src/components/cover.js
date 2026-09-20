// Обложка трека: настоящая картинка из источника (track.cover_url), а без неё —
// детерминированная абстрактная заливка в палитре VK-минимализма по id.
// Свой escape вместо импорта из trackRow — trackRow сам импортирует cover (цикл).
import { icon } from "./icons.js";

function escapeAttr(value) {
  return String(value).replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
}

const VARIANTS = [
  { pos: "20% 25%", glow: "rgba(59,123,254,0.5)", base: "#1c1c1f", deep: "#2b3f7a" },
  { pos: "75% 20%", glow: "rgba(238,63,200,0.42)", base: "#1c1c1f", deep: "#5c2b63" },
  { pos: "30% 75%", glow: "rgba(123,70,232,0.45)", base: "#1c1c1f", deep: "#3a2f70" },
  { pos: "70% 70%", glow: "rgba(59,123,254,0.4)", base: "#1c1c1f", deep: "#24427d" },
  { pos: "50% 15%", glow: "rgba(238,63,200,0.36)", base: "#1c1c1f", deep: "#4a2a6b" },
  { pos: "25% 55%", glow: "rgba(123,70,232,0.42)", base: "#1c1c1f", deep: "#33306e" },
];

function pick(track) {
  // Math.abs: у минусов id отрицательный, а -1 % 6 === -1 в JS → undefined.
  // У кандидатов живого поиска id строковый («live:<ref>») — там считаем по строке,
  // иначе Math.abs даёт NaN и заглушка падает вместо того, чтобы просто отрисоваться.
  const id = track.id;
  if (typeof id === "number" && Number.isFinite(id)) {
    return VARIANTS[Math.abs(id) % VARIANTS.length];
  }
  const text = String(id == null ? "" : id);
  let sum = 0;
  for (let i = 0; i < text.length; i += 1) sum += text.charCodeAt(i);
  return VARIANTS[sum % VARIANTS.length];
}

export function coverStyle(track) {
  const v = pick(track);
  return [
    `radial-gradient(circle at ${v.pos}, ${v.glow}, transparent 55%)`,
    `linear-gradient(150deg, ${v.deep} 0%, ${v.base} 70%)`,
  ].join(", ");
}

// Размер обложки SoundCloud задаётся суффиксом имени файла (19.09, замер):
// «-original» до 800 КБ — его грузили даже в строку списка на 46px; «-t500x500»
// в плеере на экране ×3 выглядел мыльно, а «-t1080x1080» есть у всех (240 КБ).
const SC_SIZE = /-(original|large|crop|small|badge|tiny|mini|t\d+x\d+)\.(jpe?g|png)(\?.*)?$/i;

export function sizedCover(url, big = false) {
  if (!url || !/sndcdn\.com\//.test(url) || !SC_SIZE.test(url)) return url;
  // Аватарки (обложка трека без своей картинки) крупнее 500 не бывают, а
  // «-t1080x1080» у них — растянутая мелочь того же качества
  const size = big && !/\/avatars-/.test(url) ? "t1080x1080" : big ? "t500x500" : "t300x300";
  return url.replace(SC_SIZE, `-${size}.$2`);
}

function hiResCover(url, className) {
  return sizedCover(url, className === "player-art");
}

// Обложка заполняет квадрат целиком (object-fit: cover) — решение владельца 19.09:
// полосы по бокам и размытая подложка выглядели как рамка больше картинки.
export function renderCover(track, className = "track-cover") {
  if (track.cover_url) {
    const src = escapeAttr(hiResCover(track.cover_url, className));
    // При ошибке загрузки картинка убирается — остаётся градиентная заглушка
    return `
      <div class="${className} cover-art" style="background:${coverStyle(track)}">
        <img class="cover-img" src="${src}" alt="" loading="lazy" onerror="this.remove()" />
      </div>
    `;
  }
  return `
    <div class="${className} cover-art" style="background:${coverStyle(track)}">
      <span class="cover-facet"></span>
      <span class="cover-note-icon">${icon("note")}</span>
    </div>
  `;
}

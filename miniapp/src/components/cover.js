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
  // Math.abs: у минусов id отрицательный, а -1 % 6 === -1 в JS → undefined
  return VARIANTS[Math.abs(track.id) % VARIANTS.length];
}

export function coverStyle(track) {
  const v = pick(track);
  return [
    `radial-gradient(circle at ${v.pos}, ${v.glow}, transparent 55%)`,
    `linear-gradient(150deg, ${v.deep} 0%, ${v.base} 70%)`,
  ].join(", ");
}

// withBlur — для крупных обложек (плеер): показываем всю обложку целиком
// (object-fit: contain), а пустоты по бокам у неквадратных источников (YouTube
// 16:9) закрываем размытой копией той же картинки. В списках это не нужно —
// там 46px и лишний размытый слой только грузит рендер.
export function renderCover(track, className = "track-cover", withBlur = false) {
  if (track.cover_url) {
    const src = escapeAttr(track.cover_url);
    // При ошибке загрузки убираем обе картинки — остаётся градиентная заглушка
    const blur = withBlur
      ? `<img class="cover-blur" src="${src}" alt="" aria-hidden="true" loading="lazy" onerror="this.remove()" />`
      : "";
    return `
      <div class="${className} cover-art${withBlur ? " cover-art--fit" : ""}" style="background:${coverStyle(track)}">
        ${blur}
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

// Настоящих обложек в базе нет — вместо плоской заливки с буквой генерируем
// абстрактный «кристалл аметиста»: слоистые radial-градиенты + блик, как на
// референсе (глубокие тени + светящаяся грань). Один трек — всегда одна и та же
// обложка (детерминировано по id).
import { icon } from "./icons.js";

const VARIANTS = [
  { pos: "20% 25%", glow: "rgba(192,120,255,0.55)", base: "#1b1028", deep: "#3b1266" },
  { pos: "75% 20%", glow: "rgba(155,77,255,0.5)", base: "#150f22", deep: "#4a1a7d" },
  { pos: "30% 75%", glow: "rgba(213,166,255,0.45)", base: "#170f24", deep: "#5c1f94" },
  { pos: "70% 70%", glow: "rgba(176,103,255,0.5)", base: "#140c20", deep: "#6425a8" },
  { pos: "50% 15%", glow: "rgba(200,140,255,0.5)", base: "#190f28", deep: "#3b1266" },
  { pos: "25% 55%", glow: "rgba(155,77,255,0.55)", base: "#120c1e", deep: "#2a1240" },
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

export function renderCover(track, className = "track-cover") {
  return `
    <div class="${className} cover-art" style="background:${coverStyle(track)}">
      <span class="cover-facet"></span>
      <span class="cover-note-icon">${icon("note")}</span>
    </div>
  `;
}

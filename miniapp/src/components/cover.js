// Обложек в базе нет — генерируем детерминированный аметистовый градиент
// по id трека + первая буква исполнителя. Один трек всегда выглядит одинаково.

const GRADIENTS = [
  "linear-gradient(135deg, #3b1266, #6425a8)",
  "linear-gradient(135deg, #241238, #7c35d9)",
  "linear-gradient(135deg, #1b1028, #9b4dff)",
  "linear-gradient(135deg, #4a1a7d, #2a1240)",
  "linear-gradient(135deg, #5c1f94, #120d1a)",
  "linear-gradient(135deg, #6425a8, #c078ff)",
];

export function coverStyle(track) {
  return GRADIENTS[track.id % GRADIENTS.length];
}

export function coverLetter(track) {
  const source = (track.artist || track.title || "♪").trim();
  return source ? source[0].toUpperCase() : "♪";
}

export function renderCover(track, className = "track-cover") {
  return `
    <div class="${className}" style="background:${coverStyle(track)}">
      <span class="cover-letter">${coverLetter(track)}</span>
    </div>
  `;
}

// Тонкие одноцветные line-иконки (stroke=currentColor) — без внешних шрифтов/CDN.
const WRAP = (inner) =>
  `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${inner}</svg>`;

const PATHS = {
  home: '<path d="M4 11.5 12 4l8 7.5"/><path d="M6 10v9a1 1 0 0 0 1 1h4v-6h2v6h4a1 1 0 0 0 1-1v-9"/>',
  search: '<circle cx="11" cy="11" r="6.5"/><path d="m20 20-4.3-4.3"/>',
  library: '<rect x="4" y="4" width="6" height="16" rx="1.5"/><rect x="14" y="8" width="6" height="12" rx="1.5"/>',
  settings:
    '<circle cx="12" cy="12" r="3"/><path d="M19.4 13.5a1.7 1.7 0 0 0 .34 1.87l.06.06a2.05 2.05 0 1 1-2.9 2.9l-.06-.06a1.7 1.7 0 0 0-1.87-.34 1.7 1.7 0 0 0-1 1.55V20a2.05 2.05 0 0 1-4.1 0v-.1a1.7 1.7 0 0 0-1.1-1.55 1.7 1.7 0 0 0-1.87.34l-.06.06a2.05 2.05 0 1 1-2.9-2.9l.06-.06a1.7 1.7 0 0 0 .34-1.87 1.7 1.7 0 0 0-1.55-1H4a2.05 2.05 0 0 1 0-4.1h.1a1.7 1.7 0 0 0 1.55-1.1 1.7 1.7 0 0 0-.34-1.87l-.06-.06a2.05 2.05 0 1 1 2.9-2.9l.06.06a1.7 1.7 0 0 0 1.87.34H10a1.7 1.7 0 0 0 1-1.55V4a2.05 2.05 0 0 1 4.1 0v.1a1.7 1.7 0 0 0 1 1.55 1.7 1.7 0 0 0 1.87-.34l.06-.06a2.05 2.05 0 1 1 2.9 2.9l-.06.06a1.7 1.7 0 0 0-.34 1.87V10c.14.45.55 1 1.55 1H20a2.05 2.05 0 0 1 0 4.1h-.1a1.7 1.7 0 0 0-1.5 1.4Z"/>',
  play: '<path d="M7 5.5v13l11-6.5-11-6.5Z" fill="currentColor" stroke="none"/>',
  pause: '<rect x="6.5" y="5" width="4" height="14" rx="1" fill="currentColor" stroke="none"/><rect x="13.5" y="5" width="4" height="14" rx="1" fill="currentColor" stroke="none"/>',
  prev: '<path d="M18 6 8 12l10 6V6Z" fill="currentColor" stroke="none"/><rect x="5" y="6" width="2" height="12" rx="1" fill="currentColor" stroke="none"/>',
  next: '<path d="M6 6l10 6L6 18V6Z" fill="currentColor" stroke="none"/><rect x="17" y="6" width="2" height="12" rx="1" fill="currentColor" stroke="none"/>',
  shuffle:
    '<path d="M3 6h3.5L15 17h6"/><path d="M17.5 6H21v3.5"/><path d="M3 17.5h3.5L11 12"/><path d="m7.5 8.5-2-2.5 2-2.5" transform="translate(0 0)"/><path d="M17.5 14 21 17.5 17.5 21"/><path d="M21 6l-3.5 3.5"/>',
  repeat: '<path d="M4 7h13a3 3 0 0 1 3 3v1"/><path d="m14 3 3 4-3 4"/><path d="M20 17H7a3 3 0 0 1-3-3v-1"/><path d="m10 21-3-4 3-4"/>',
  heart: '<path d="M12 20.2s-7.6-4.6-9.9-9.2C.6 7.3 2.7 4 6.2 4c2 0 3.5 1 4.9 2.6C12.4 5 13.9 4 15.9 4c3.5 0 5.6 3.3 4.1 7-2.3 4.6-9.9 9.2-9.9 9.2Z"/>',
  download: '<path d="M12 4v11"/><path d="m7.5 11 4.5 4.5L16.5 11"/><path d="M5 19.5h14"/>',
  clock: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
  playlist: '<path d="M4 6h13"/><path d="M4 12h13"/><path d="M4 18h8"/><circle cx="19" cy="17" r="2.4"/><path d="M21.4 17V8l-3 1"/>',
  plus: '<path d="M12 5v14"/><path d="M5 12h14"/>',
  check: '<path d="m5 12.5 4.5 4.5L19 7"/>',
  more: '<circle cx="5" cy="12" r="1.4" fill="currentColor" stroke="none"/><circle cx="12" cy="12" r="1.4" fill="currentColor" stroke="none"/><circle cx="19" cy="12" r="1.4" fill="currentColor" stroke="none"/>',
  share: '<circle cx="18" cy="5.5" r="2.3"/><circle cx="6" cy="12" r="2.3"/><circle cx="18" cy="18.5" r="2.3"/><path d="m8.1 10.8 7.8-4.2"/><path d="m8.1 13.2 7.8 4.2"/>',
  close: '<path d="m6 6 12 12"/><path d="M18 6 6 18"/>',
  chevron: '<path d="m9 6 6 6-6 6"/>',
  back: '<path d="m15 6-6 6 6 6"/>',
  "chevron-down": '<path d="m6 9 6 6 6-6"/>',
  note: '<circle cx="8" cy="17.5" r="2.6"/><path d="M10.6 17.5V5.8l7.4-1.6v10.2"/><circle cx="18" cy="15.4" r="2.6"/>',
  crown: '<path d="M4 8.5 8 12l4-6.5L16 12l4-3.5L18.5 18h-13Z"/><path d="M6.5 20h11"/>',
  bell: '<path d="M6.5 10a5.5 5.5 0 0 1 11 0c0 4 1.5 5.5 1.5 5.5h-14S6.5 14 6.5 10Z"/><path d="M10 19a2 2 0 0 0 4 0"/>',
  lock: '<rect x="5.5" y="10.5" width="13" height="9" rx="2"/><path d="M8.5 10.5V7.5a3.5 3.5 0 0 1 7 0v3"/>',
  doc: '<path d="M7 3.5h7l4 4V20a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4.5a1 1 0 0 1 1-1Z"/><path d="M14 3.5V8h4"/>',
  font: '<path d="M6 19 10.5 6h1.6L16.5 19"/><path d="M7.3 15h7"/><path d="M18 19v-6.5"/><path d="m16 14 2-1.8 2 1.8"/>',
  help: '<circle cx="12" cy="12" r="8.5"/><path d="M9.6 9.3a2.4 2.4 0 1 1 3.5 2.1c-.9.5-1.4 1-1.4 2"/><circle cx="12" cy="16.3" r="0.4" fill="currentColor" stroke="none"/>',
  theme: '<path d="M12 3.5a8.5 8.5 0 1 0 8.5 8.5A6.5 6.5 0 0 1 12 3.5Z"/>',
  logout: '<path d="M9 4H6a1.5 1.5 0 0 0-1.5 1.5v13A1.5 1.5 0 0 0 6 20h3"/><path d="M15.5 16.5 20 12l-4.5-4.5"/><path d="M20 12H9"/>',
};

export function icon(name) {
  return WRAP(PATHS[name] || "");
}

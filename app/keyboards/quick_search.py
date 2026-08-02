"""Клавиатура выдачи живого поиска в боте (формат по скринам владельца):
кнопка на каждый трек «2:19 Артист - Название» + пагинация внизу.

Кнопка ссылается на ИНДЕКС кандидата в списке, лежащем в FSM, а не на ссылку
источника: Telegram даёт под callback_data 64 байта, одна ссылка SoundCloud
съедает больше.
"""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.services.track_lookup.ranking import Candidate

PAGE_SIZE = 10
_MAX_BUTTON_TEXT = 60  # Telegram обрежет длиннее — режем сами, чтобы не терять хвост смысла


def _duration_label(seconds: int) -> str:
    minutes, rest = divmod(max(0, seconds or 0), 60)
    return f"{minutes}:{rest:02d}"


def candidate_button_text(candidate: Candidate) -> str:
    """«2:19 kizaru - AFK». Длительность 0 — источник её не сообщил, время скрываем."""
    name = candidate.title.strip()
    if candidate.artist and candidate.artist.lower() not in name.lower():
        name = f"{candidate.artist} - {name}"
    label = f"{_duration_label(candidate.duration)} {name}" if candidate.duration else name
    if len(label) <= _MAX_BUTTON_TEXT:
        return label
    return label[: _MAX_BUTTON_TEXT - 1] + "…"


def page_slice(candidates: list[Candidate], page: int) -> list[Candidate]:
    start = (page - 1) * PAGE_SIZE
    return candidates[start : start + PAGE_SIZE]


def total_pages(candidates: list[Candidate]) -> int:
    return max(1, -(-len(candidates) // PAGE_SIZE))


def quick_search_keyboard(candidates: list[Candidate], page: int) -> InlineKeyboardMarkup:
    """Страница выдачи. Стрелки показываются только там, где есть куда идти."""
    pages = total_pages(candidates)
    offset = (page - 1) * PAGE_SIZE
    rows = [
        [
            InlineKeyboardButton(
                text=candidate_button_text(candidate),
                callback_data=f"qs:c:{offset + position}",
            )
        ]
        for position, candidate in enumerate(page_slice(candidates, page))
    ]

    nav: list[InlineKeyboardButton] = []
    if page > 1:
        nav.append(InlineKeyboardButton(text="«", callback_data=f"qs:p:{page - 1}"))
    nav.append(InlineKeyboardButton(text=f"{page} / {pages}", callback_data="qs:noop"))
    if page < pages:
        nav.append(InlineKeyboardButton(text="»", callback_data=f"qs:p:{page + 1}"))
    if len(nav) > 1:
        rows.append(nav)

    return InlineKeyboardMarkup(inline_keyboard=rows)

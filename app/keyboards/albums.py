"""Клавиатуры альбомов в боте (16.09): строки альбомов под выдачей и экран альбома.

Как и в выдаче треков, кнопки ссылаются на ИНДЕКС в списке из FSM, а не на
ссылку источника: под callback_data Telegram даёт 64 байта.
"""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.i18n import t
from app.keyboards.quick_search import candidate_button_text
from app.services.albums import AlbumCandidate
from app.services.track_lookup.ranking import Candidate

PAGE_SIZE = 10
_MAX_BUTTON_TEXT = 60


def _cut(text: str) -> str:
    return text if len(text) <= _MAX_BUTTON_TEXT else text[: _MAX_BUTTON_TEXT - 1] + "…"


def album_rows(albums: list[AlbumCandidate]) -> list[list[InlineKeyboardButton]]:
    """Блок «💿 Альбомы» для низа выдачи. Пусто — блока нет вовсе."""
    if not albums:
        return []
    rows = [[InlineKeyboardButton(text=t("album.section"), callback_data="qs:noop")]]
    for index, album in enumerate(albums):
        label = t("album.button", artist=album.artist, title=album.title, count=album.track_count)
        rows.append([InlineKeyboardButton(text=_cut(label), callback_data=f"al:o:{index}")])
    return rows


def total_pages(tracks: list[Candidate]) -> int:
    return max(1, -(-len(tracks) // PAGE_SIZE))


def album_keyboard(tracks: list[Candidate], page: int) -> InlineKeyboardMarkup:
    """Экран альбома: треки страницей по 10, «скачать весь», назад к выдаче."""
    pages = total_pages(tracks)
    page = max(1, min(page, pages))
    offset = (page - 1) * PAGE_SIZE
    rows = [
        [
            InlineKeyboardButton(
                text=_cut(f"{offset + position + 1}. {candidate_button_text(track)}"),
                callback_data=f"al:t:{offset + position}",
            )
        ]
        for position, track in enumerate(tracks[offset : offset + PAGE_SIZE])
    ]
    nav: list[InlineKeyboardButton] = []
    if page > 1:
        nav.append(InlineKeyboardButton(text="«", callback_data=f"al:p:{page - 1}"))
    nav.append(InlineKeyboardButton(text=f"{page} / {pages}", callback_data="qs:noop"))
    if page < pages:
        nav.append(InlineKeyboardButton(text="»", callback_data=f"al:p:{page + 1}"))
    if len(nav) > 1:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text=t("album.download_all", count=len(tracks)), callback_data="al:all")])
    rows.append([InlineKeyboardButton(text=t("album.back"), callback_data="qs:p:1")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def premium_offer_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=t("album.premium_button"), callback_data="menu:premium")]]
    )

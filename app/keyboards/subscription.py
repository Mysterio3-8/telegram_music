from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.db.models import RequiredChannel


def _row_url(row: RequiredChannel) -> str | None:
    """Кнопка-ссылка гейта. None — показать нечего (приватный канал без username)."""
    if row.kind == "bot":
        return row.channel  # для ботов хранится полная t.me-ссылка (с deep-link параметром)
    if row.channel.startswith("@"):
        return f"https://t.me/{row.channel.removeprefix('@')}"
    return None  # -100… без username по ссылке не открыть


def subscription_gate_keyboard(channels: list[RequiredChannel]) -> InlineKeyboardMarkup:
    rows = []
    for row in channels:
        url = _row_url(row)
        if url:
            rows.append([InlineKeyboardButton(text=row.label, url=url)])
    rows.append([InlineKeyboardButton(text="✅ Проверить подписку", callback_data="sub:check")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

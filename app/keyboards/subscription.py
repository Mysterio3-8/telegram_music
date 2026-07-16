from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.db.models import RequiredChannel


def _channel_url(channel: str) -> str:
    handle = channel.removeprefix("@")
    return f"https://t.me/{handle}"


def subscription_gate_keyboard(channels: list[RequiredChannel]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=row.label, url=_channel_url(row.channel))]
        for row in channels
        if row.channel.startswith("@")  # приватные (-100…) без username не откроешь по ссылке
    ]
    rows.append([InlineKeyboardButton(text="✅ Проверить подписку", callback_data="sub:check")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

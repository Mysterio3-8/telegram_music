from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.config import settings


def _channel_url(channel: str) -> str:
    handle = channel.removeprefix("@")
    return f"https://t.me/{handle}"


def subscription_gate_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=label, url=_channel_url(channel))]
        for channel, label in settings.required_channels
    ]
    rows.append([InlineKeyboardButton(text="✅ Проверить подписку", callback_data="sub:check")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

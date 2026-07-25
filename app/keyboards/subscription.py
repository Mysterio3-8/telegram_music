from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.db.models import RequiredChannel
from app.services.required_channels import channel_url


def subscription_gate_keyboard(channels: list[RequiredChannel]) -> InlineKeyboardMarkup:
    rows = []
    for row in channels:
        url = channel_url(row)
        if url:
            rows.append([InlineKeyboardButton(text=row.label, url=url)])
    rows.append([InlineKeyboardButton(text="✅ Проверить подписку", callback_data="sub:check")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

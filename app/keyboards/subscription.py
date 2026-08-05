from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.db.models import RequiredChannel
from app.i18n import DEFAULT_LANGUAGE, t
from app.services.required_channels import channel_url


def subscription_gate_keyboard(
    channels: list[RequiredChannel], lang: str = DEFAULT_LANGUAGE
) -> InlineKeyboardMarkup:
    rows = []
    for row in channels:
        url = channel_url(row)
        if url:
            # Название канала — данные владельца, не переводим
            rows.append([InlineKeyboardButton(text=row.label, url=url)])
    rows.append([InlineKeyboardButton(text=t("gate.check", lang), callback_data="sub:check")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

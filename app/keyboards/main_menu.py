from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from app.config import settings


def main_menu_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="⬆️ Загрузить трек", callback_data="menu:upload")],
        # Перенос плейлистов живёт в Mini App (решение владельца): в боте кнопка
        # лишняя. Команда /transfer и обработчик menu:transfer оставлены рабочими.
        [
            InlineKeyboardButton(
                text=f"💎 Открыть плеер — {settings.premium_price_rub} ₽/мес",
                callback_data="menu:premium",
            )
        ],
        [
            InlineKeyboardButton(
                text="🆘 Поддержка / жалобы / идеи",
                url=f"https://t.me/{settings.support_bot_username}",
            )
        ],
    ]
    if settings.public_base_url:
        rows.insert(
            0,
            [
                InlineKeyboardButton(
                    text="🎧 Открыть плеер",
                    web_app=WebAppInfo(url=settings.public_base_url),
                )
            ],
        )
    # menu:miniapp в stubs.py оставлен, чтобы кнопка в старых сообщениях не была мёртвой
    return InlineKeyboardMarkup(inline_keyboard=rows)

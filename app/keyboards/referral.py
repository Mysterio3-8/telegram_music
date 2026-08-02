"""Клавиатура реферального экрана в боте.

«Скопировать» тут не сделать — у Bot API нет доступа к буферу обмена. Вместо
этого ссылка выводится в тексте моноширинным блоком: тап по ней в Telegram
копирует её целиком. Кнопка ведёт в системный шеринг.
"""
from urllib.parse import quote

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

_SHARE_TEXT = (
    "Держи бота, где можно найти и скачать любой трек бесплатно — "
    "просто пишешь название, и он присылает музыку."
)


def share_url(link: str) -> str:
    return f"https://t.me/share/url?url={quote(link, safe='')}&text={quote(_SHARE_TEXT)}"


def referral_keyboard(link: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📤 Пригласить друга", url=share_url(link))],
            [InlineKeyboardButton(text="🔄 Обновить", callback_data="ref:refresh")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:main")],
        ]
    )

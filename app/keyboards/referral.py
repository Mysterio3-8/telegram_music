"""Клавиатура реферального экрана в боте.

«Скопировать» тут не сделать — у Bot API нет доступа к буферу обмена. Вместо
этого ссылка выводится в тексте моноширинным блоком: тап по ней в Telegram
копирует её целиком. Кнопка ведёт в системный шеринг.
"""
from urllib.parse import quote

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.i18n import t


def share_url(link: str) -> str:
    """Текст шеринга — на языке приглашающего: он его и прочитает перед отправкой."""
    return f"https://t.me/share/url?url={quote(link, safe='')}&text={quote(t('referral.share_text'))}"


def referral_keyboard(link: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t("referral.invite_button"), url=share_url(link))],
            [InlineKeyboardButton(text=t("referral.refresh"), callback_data="ref:refresh")],
            [InlineKeyboardButton(text=t("common.back_arrow"), callback_data="menu:main")],
        ]
    )

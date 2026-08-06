from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from app.config import settings
from app.db.models import Contest
from app.services.contests import contest_channel_url
from app.i18n import t


def contest_keyboard(contest: Contest, joined: bool) -> InlineKeyboardMarkup:
    """Кнопки под постом конкурса: подписка на канал, участие, вход в плеер."""
    rows: list[list[InlineKeyboardButton]] = []

    channel = contest_channel_url(contest)
    if channel:
        rows.append([InlineKeyboardButton(text=t("contest.subscribe"), url=channel)])

    action = t("contest.participating") if joined else t("contest.join")
    rows.append([InlineKeyboardButton(text=action, callback_data=f"contest:join:{contest.id}")])

    if settings.public_base_url:
        rows.append(
            [
                InlineKeyboardButton(
                    text=t("contest.open_app"),
                    web_app=WebAppInfo(url=settings.public_base_url),
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)
